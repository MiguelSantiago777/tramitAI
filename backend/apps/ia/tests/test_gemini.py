import json
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors, types

from apps.ia.llm import LlmError, LlmRefusal, LlmRequest
from apps.ia.llm.gemini_client import GeminiLlmClient

REQUEST = LlmRequest(
    system="Você é a Vera.", user_content="<conversa>oi</conversa>", json_schema={"type": "object"}
)


def _response(text: str, finish: Any = types.FinishReason.STOP, **extra: Any):
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=[types.Part(text=text)]),
                finish_reason=finish,
            )
        ],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=120, candidates_token_count=40, thoughts_token_count=10
        ),
        model_version="gemini-teste",
        **extra,
    )


class FakeModels:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _client(result: Any) -> tuple[GeminiLlmClient, FakeModels]:
    models = FakeModels(result)
    return GeminiLlmClient(client=SimpleNamespace(models=models)), models


def test_success_sends_schema_and_parses_json(settings):
    settings.LLM_MODEL = "gemini-3.8-flash"
    client, models = _client(_response(json.dumps({"reply": "Olá!"})))

    result = client.complete(REQUEST)

    assert result.data == {"reply": "Olá!"}
    assert (result.provider, result.model) == ("gemini", "gemini-teste")
    assert (result.input_tokens, result.output_tokens) == (120, 50)
    [call] = models.calls
    assert call["model"] == "gemini-3.8-flash"
    assert call["contents"] == REQUEST.user_content
    assert call["config"].system_instruction == "Você é a Vera."
    assert call["config"].response_mime_type == "application/json"
    assert call["config"].response_json_schema == {"type": "object"}


def test_safety_block_is_refusal():
    client, _ = _client(_response("", finish=types.FinishReason.SAFETY))
    with pytest.raises(LlmRefusal):
        client.complete(REQUEST)


def test_prompt_block_is_refusal():
    blocked = _response(
        "",
        prompt_feedback=types.GenerateContentResponsePromptFeedback(
            block_reason=types.BlockedReason.SAFETY
        ),
    )
    client, _ = _client(blocked)
    with pytest.raises(LlmRefusal):
        client.complete(REQUEST)


@pytest.mark.parametrize(("code", "retryable"), [(429, True), (503, True), (400, False)])
def test_api_errors(code, retryable):
    cls = errors.ServerError if code >= 500 else errors.ClientError
    client, _ = _client(cls(code, {"error": {"message": "x", "status": "X"}}))
    with pytest.raises(LlmError) as exc:
        client.complete(REQUEST)
    assert exc.value.retryable is retryable


def test_invalid_json_and_max_tokens():
    client, _ = _client(_response("não é json"))
    with pytest.raises(LlmError) as bad:
        client.complete(REQUEST)
    assert bad.value.code == "invalid_json"

    client, _ = _client(_response('{"reply": "Ol', finish=types.FinishReason.MAX_TOKENS))
    with pytest.raises(LlmError) as cut:
        client.complete(REQUEST)
    assert cut.value.code == "max_tokens"


class SequenceModels:
    """Primeiro modelo sobrecarregado, o reserva responde."""

    def __init__(self, results: dict[str, Any]) -> None:
        self.results = results
        self.calls: list[str] = []

    def generate_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs["model"])
        result = self.results[kwargs["model"]]
        if isinstance(result, Exception):
            raise result
        return result


def _overloaded() -> errors.ServerError:
    return errors.ServerError(503, {"error": {"code": 503, "status": "UNAVAILABLE"}})


def test_overloaded_model_falls_back_to_reserve_right_away(settings):
    settings.LLM_MODEL = "gemini-3.8-flash"
    settings.LLM_FALLBACK_MODELS = ["gemini-3.8-flash-lite"]
    models = SequenceModels(
        {
            "gemini-3.8-flash": _overloaded(),
            "gemini-3.8-flash-lite": _response(json.dumps({"reply": "Oi!"})),
        }
    )
    result = GeminiLlmClient(client=SimpleNamespace(models=models)).complete(REQUEST)
    assert result.data == {"reply": "Oi!"}
    assert models.calls == ["gemini-3.8-flash", "gemini-3.8-flash-lite"]


def test_all_models_overloaded_is_retryable(settings):
    settings.LLM_MODEL = "a"
    settings.LLM_FALLBACK_MODELS = ["b"]
    models = SequenceModels({"a": _overloaded(), "b": _overloaded()})
    with pytest.raises(LlmError) as raised:
        GeminiLlmClient(client=SimpleNamespace(models=models)).complete(REQUEST)
    assert raised.value.retryable
    assert models.calls == ["a", "b"]


def test_definitive_error_does_not_try_reserve(settings):
    settings.LLM_MODEL = "a"
    settings.LLM_FALLBACK_MODELS = ["b"]
    bad = errors.ClientError(400, {"error": {"code": 400, "status": "INVALID_ARGUMENT"}})
    models = SequenceModels({"a": bad, "b": _response("{}")})
    with pytest.raises(LlmError):
        GeminiLlmClient(client=SimpleNamespace(models=models)).complete(REQUEST)
    assert models.calls == ["a"]


def test_thinking_level_is_sent_when_configured(settings):
    settings.LLM_THINKING_LEVEL = "low"
    client, models = _client(_response(json.dumps({"reply": "ok"})))
    client.complete(REQUEST)
    assert models.calls[0]["config"].thinking_config.thinking_level == types.ThinkingLevel.LOW

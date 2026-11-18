import json
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors, types

from apps.ia.llm import LlmError, LlmRefusal, LlmRequest
from apps.ia.llm.gemini_client import GeminiLlmClient

REQUEST = LlmRequest(
    system="Você é a Lia.", user_content="<conversa>oi</conversa>", json_schema={"type": "object"}
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
    assert call["config"].system_instruction == "Você é a Lia."
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

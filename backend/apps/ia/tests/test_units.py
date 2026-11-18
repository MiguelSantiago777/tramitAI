from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from apps.ia.consent import is_acceptance_text
from apps.ia.guardrails import check_reply
from apps.ia.llm import LlmError, LlmRefusal, LlmRequest
from apps.ia.llm.anthropic_client import REFUSAL_FALLBACK_BETA, AnthropicLlmClient
from apps.ia.prompts import load_prompt
from apps.ia.triage import TRIAGE_SCHEMA, InvalidTriage, parse_triage


@pytest.mark.parametrize(
    "text",
    ["Aceito", "aceito!", "ACEITO.", "Sim, aceito", "eu aceito", "Aceito o termo", "ok aceito"],
)
def test_acceptance_text(text):
    assert is_acceptance_text(text)


@pytest.mark.parametrize(
    "text", ["Não aceito", "aceito pagar em 3x?", "Quero saber se aceitam cartão", "", "aceita"]
)
def test_not_acceptance_text(text):
    assert not is_acceptance_text(text)


def test_guardrails_allow_plain_reply():
    assert check_reply("Obrigado! Vou verificar com o advogado e já te retorno.", "") == []


def test_guardrails_court_name_is_not_a_citation():
    assert check_reply("Seu processo está no TJRJ.", "TJRJ") == []


def test_parse_triage_normalizes_unknown_enums():
    result = parse_triage(
        {
            "intent": "xyz",
            "urgency": "urgentíssimo",
            "needs_lawyer": True,
            "summary_for_lawyer": "s",
            "reply": "r",
        }
    )
    assert (result.intent, result.urgency) == ("other", "normal")


@pytest.mark.parametrize(
    "data",
    [
        {},
        {
            "intent": "x",
            "urgency": "low",
            "needs_lawyer": "sim",
            "summary_for_lawyer": "",
            "reply": "r",
        },
        {
            "intent": "x",
            "urgency": "low",
            "needs_lawyer": True,
            "summary_for_lawyer": "",
            "reply": " ",
        },
    ],
)
def test_parse_triage_rejects_invalid(data):
    with pytest.raises(InvalidTriage):
        parse_triage(data)


def test_prompts_are_versioned_files():
    prompt = load_prompt("triage")
    assert prompt.version == "v2"
    assert "triage_complete" in prompt.text
    assert load_prompt("triage", "v1").version == "v1"  # versões antigas ficam (auditoria)
    assert "Nunca inventa" in prompt.text
    assert "{termo}" in load_prompt("term_request").text


# ------------------------------------------------------------------ adapter Anthropic


class _FakeMessages:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.kwargs = response, error, None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.response


def _sdk(response=None, error=None):
    messages = _FakeMessages(response, error)
    return SimpleNamespace(messages=messages, beta=SimpleNamespace(messages=messages)), messages


def _response(text, stop_reason="end_turn"):
    return SimpleNamespace(
        stop_reason=stop_reason,
        stop_details=SimpleNamespace(category="cyber") if stop_reason == "refusal" else None,
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=text),
        ],
        model="claude-opus-5-5",
        usage=SimpleNamespace(input_tokens=120, output_tokens=40),
        _request_id="req_123",
    )


REQUEST = LlmRequest(system="sys", user_content="ctx", json_schema=TRIAGE_SCHEMA)


def test_anthropic_adapter_sends_structured_output_and_fallback(settings):
    settings.LLM_MODEL = "claude-opus-5-5"
    settings.LLM_EFFORT = "medium"
    settings.LLM_REFUSAL_FALLBACK = True
    sdk, messages = _sdk(_response('{"reply": "oi"}'))

    result = AnthropicLlmClient(client=sdk).complete(REQUEST)

    assert result.data == {"reply": "oi"}
    assert (result.input_tokens, result.output_tokens, result.request_id) == (120, 40, "req_123")
    sent = messages.kwargs
    assert sent["model"] == "claude-opus-5-5"
    assert sent["system"] == "sys"
    assert sent["messages"] == [{"role": "user", "content": "ctx"}]
    assert sent["output_config"]["effort"] == "medium"
    assert sent["output_config"]["format"] == {"type": "json_schema", "schema": TRIAGE_SCHEMA}
    assert sent["betas"] == [REFUSAL_FALLBACK_BETA]
    assert sent["fallbacks"] == "default"
    assert "temperature" not in sent


def test_anthropic_adapter_refusal():
    sdk, _ = _sdk(_response("", stop_reason="refusal"))
    with pytest.raises(LlmRefusal) as info:
        AnthropicLlmClient(client=sdk).complete(REQUEST)
    assert info.value.detail == "cyber"


def test_anthropic_adapter_max_tokens_is_not_retryable():
    sdk, _ = _sdk(_response('{"reply": "o', stop_reason="max_tokens"))
    with pytest.raises(LlmError) as info:
        AnthropicLlmClient(client=sdk).complete(REQUEST)
    assert (info.value.code, info.value.retryable) == ("max_tokens", False)


def _status_error(cls, status):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx2.Response(status, request=request)
    return cls(message="erro", response=response, body=None)


@pytest.mark.parametrize(
    ("error", "code", "retryable"),
    [
        (_status_error(anthropic.RateLimitError, 429), "rate_limited", True),
        (_status_error(anthropic.InternalServerError, 500), "http_500", True),
        (_status_error(anthropic.BadRequestError, 400), "http_400", False),
        (
            anthropic.APIConnectionError(
                request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
            ),
            "connection",
            True,
        ),
    ],
)
def test_anthropic_adapter_error_mapping(error, code, retryable):
    sdk, _ = _sdk(error=error)
    with pytest.raises(LlmError) as info:
        AnthropicLlmClient(client=sdk).complete(REQUEST)
    assert (info.value.code, info.value.retryable) == (code, retryable)

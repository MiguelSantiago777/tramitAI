"""Adapter da API Gemini (Google AI Studio), SDK oficial `google-genai`.

- Saída estruturada com `response_json_schema` (JSON Schema): resposta em JSON.
- Modelo vem de LLM_MODEL; chave em GEMINI_API_KEY.
- Bloqueio por segurança do Google vira LlmRefusal (mesmo tratamento da Anthropic).
- Nada de conteúdo em log: só códigos e contagem de tokens.

ATENÇÃO (LGPD/sigilo): no plano gratuito do Gemini, o Google pode usar o conteúdo enviado
para melhorar os produtos. Para mensagens reais de clientes, use uma chave com faturamento
ativo (plano pago). Ver README, seção "IA".
"""

import json
import logging
import time
from typing import Any

import httpx
from django.conf import settings
from google import genai
from google.genai import errors, types

from .base import LlmError, LlmRefusal, LlmRequest, LlmResult

logger = logging.getLogger(__name__)

# Motivos de parada que significam "o provedor bloqueou o conteúdo".
_BLOCKED = {
    "SAFETY",
    "RECITATION",
    "BLOCKLIST",
    "PROHIBITED_CONTENT",
    "SPII",
}


class GeminiLlmClient:
    provider = "gemini"

    def __init__(self, client: Any | None = None) -> None:
        self._client = client or genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=int(settings.LLM_TIMEOUT_SECONDS * 1000)),
        )

    def complete(self, request: LlmRequest) -> LlmResult:
        config = types.GenerateContentConfig(
            system_instruction=request.system,
            response_mime_type="application/json",
            response_json_schema=request.json_schema,
            max_output_tokens=settings.LLM_MAX_TOKENS,
        )
        started = time.monotonic()
        try:
            response = self._client.models.generate_content(
                model=settings.LLM_MODEL, contents=request.user_content, config=config
            )
        except errors.APIError as exc:
            code = int(getattr(exc, "code", 0) or 0)
            # Status e mensagem do Google explicam o erro (chave, modelo, schema) e não trazem
            # o conteúdo enviado; o texto da conversa continua fora do log.
            logger.warning(
                "llm http error code=%s status=%s message=%s",
                code,
                getattr(exc, "status", ""),
                str(getattr(exc, "message", "") or "")[:300],
            )
            if code == 429:
                raise LlmError("rate_limited", retryable=True) from exc
            raise LlmError(f"http_{code}", retryable=code >= 500) from exc
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise LlmError("connection", retryable=True, detail=type(exc).__name__) from exc
        latency_ms = int((time.monotonic() - started) * 1000)
        request_id = str(getattr(response, "response_id", "") or "")

        feedback = getattr(response, "prompt_feedback", None)
        block_reason = getattr(feedback, "block_reason", None)
        if block_reason:
            logger.warning("llm blocked (prompt) reason=%s", _name(block_reason))
            raise LlmRefusal(_name(block_reason))

        candidate = (response.candidates or [None])[0]
        finish = _name(getattr(candidate, "finish_reason", None))
        if finish in _BLOCKED:
            logger.warning("llm blocked reason=%s", finish)
            raise LlmRefusal(finish)
        if finish == "MAX_TOKENS":
            raise LlmError("max_tokens", retryable=False)

        text = response.text or ""
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise LlmError("invalid_json", retryable=False) from exc
        if not isinstance(data, dict):
            raise LlmError("invalid_json", retryable=False)

        usage = response.usage_metadata
        input_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
        output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0) + int(
            getattr(usage, "thoughts_token_count", 0) or 0
        )
        model = str(getattr(response, "model_version", "") or settings.LLM_MODEL)
        logger.info(
            "llm ok purpose=%s model=%s in=%s out=%s ms=%s",
            request.purpose,
            model,
            input_tokens,
            output_tokens,
            latency_ms,
        )
        return LlmResult(
            data=data,
            raw_text=text,
            provider=self.provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            request_id=request_id[:128],
        )


def _name(value: Any) -> str:
    if value is None:
        return ""
    return str(getattr(value, "name", value)).split(".")[-1]

"""Adapter da API da Anthropic (SDK oficial).

- Saída estruturada com `output_config.format` (JSON Schema): a resposta é sempre JSON válido.
- `effort` controla profundidade/custo; o modelo e o effort vêm de settings.
- Fallback do servidor quando o modelo recusa (`fallbacks: "default"`), desligável por config.
- Nada de conteúdo em log: só códigos, tokens e request_id.
"""

import json
import logging
import time
from typing import Any

import anthropic
from django.conf import settings

from .base import LlmError, LlmRefusal, LlmRequest, LlmResult

logger = logging.getLogger(__name__)

REFUSAL_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicLlmClient:
    provider = "anthropic"

    def __init__(self, client: anthropic.Anthropic | None = None) -> None:
        # Credenciais pelo ambiente (ANTHROPIC_API_KEY). O SDK já repete 2x em 429/5xx/rede.
        self._client = client or anthropic.Anthropic(
            timeout=settings.LLM_TIMEOUT_SECONDS, max_retries=2
        )

    def complete(self, request: LlmRequest) -> LlmResult:
        params: dict[str, Any] = {
            "model": settings.LLM_MODEL,
            "max_tokens": settings.LLM_MAX_TOKENS,
            "system": request.system,
            "messages": [{"role": "user", "content": request.user_content}],
            "output_config": {
                "effort": settings.LLM_EFFORT,
                "format": {"type": "json_schema", "schema": request.json_schema},
            },
        }
        started = time.monotonic()
        try:
            if settings.LLM_REFUSAL_FALLBACK:
                response = self._client.beta.messages.create(
                    **params, betas=[REFUSAL_FALLBACK_BETA], fallbacks="default"
                )
            else:
                response = self._client.messages.create(**params)
        except anthropic.RateLimitError as exc:
            raise LlmError("rate_limited", retryable=True) from exc
        except anthropic.APIConnectionError as exc:  # inclui timeout
            raise LlmError("connection", retryable=True, detail=type(exc).__name__) from exc
        except anthropic.APIStatusError as exc:
            raise LlmError(f"http_{exc.status_code}", retryable=exc.status_code >= 500) from exc
        latency_ms = int((time.monotonic() - started) * 1000)
        request_id = str(getattr(response, "_request_id", "") or "")

        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            category = str(getattr(details, "category", "") or "")
            logger.warning("llm refusal request_id=%s category=%s", request_id, category)
            raise LlmRefusal(category)
        if response.stop_reason == "max_tokens":
            raise LlmError("max_tokens", retryable=False)

        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise LlmError("invalid_json", retryable=False) from exc
        if not isinstance(data, dict):
            raise LlmError("invalid_json", retryable=False)

        usage = response.usage
        logger.info(
            "llm ok purpose=%s model=%s in=%s out=%s ms=%s request_id=%s",
            request.purpose,
            response.model,
            usage.input_tokens,
            usage.output_tokens,
            latency_ms,
            request_id,
        )
        return LlmResult(
            data=data,
            raw_text=text,
            provider=self.provider,
            model=str(response.model),
            input_tokens=int(usage.input_tokens or 0),
            output_tokens=int(usage.output_tokens or 0),
            latency_ms=latency_ms,
            request_id=request_id,
        )

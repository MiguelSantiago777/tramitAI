from functools import cache

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .base import LlmClient, LlmError, LlmRefusal, LlmRequest, LlmResult
from .fake import FakeLlmClient

__all__ = [
    "FakeLlmClient",
    "LlmClient",
    "LlmError",
    "LlmRefusal",
    "LlmRequest",
    "LlmResult",
    "get_llm_client",
]


@cache
def _build(provider: str) -> LlmClient:
    if provider == "fake":
        return FakeLlmClient()
    if provider == "anthropic":
        from .anthropic_client import AnthropicLlmClient

        return AnthropicLlmClient()
    raise ImproperlyConfigured(f"LLM_PROVIDER desconhecido: {provider}")


def get_llm_client() -> LlmClient:
    return _build(settings.LLM_PROVIDER)

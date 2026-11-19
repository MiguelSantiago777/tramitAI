"""Interface de LLM. O resto do sistema só conhece isto; o provedor é trocável por config."""

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class LlmRequest:
    system: str
    user_content: str
    json_schema: dict[str, Any]
    # Só para registro/observabilidade (nunca o conteúdo).
    purpose: str = "triage"
    # Texto longo (peça, contrato) demora mais que a triagem: sobrescreve LLM_TIMEOUT_SECONDS.
    timeout_seconds: float | None = None


@dataclass(frozen=True)
class LlmResult:
    data: dict[str, Any]
    raw_text: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    request_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class LlmError(Exception):
    """Falha ao gerar. retryable=True: vale tentar de novo (rede, 429, 5xx)."""

    def __init__(self, code: str, *, retryable: bool, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        # Só descrição técnica; nunca conteúdo da conversa.
        self.detail = detail[:255]


class LlmRefusal(LlmError):
    """O modelo recusou responder (política de segurança do provedor)."""

    def __init__(self, category: str = "") -> None:
        super().__init__("refusal", retryable=False, detail=category)


class LlmClient(Protocol):
    provider: str

    def complete(self, request: LlmRequest) -> LlmResult: ...

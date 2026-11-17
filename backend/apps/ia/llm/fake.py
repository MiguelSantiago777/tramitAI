"""Provedor falso: determinístico, local. Para dev e testes (nada sai da máquina)."""

import json
from dataclasses import dataclass, field
from typing import Any

from .base import LlmError, LlmRequest, LlmResult

DEFAULT_TRIAGE: dict[str, Any] = {
    "intent": "other",
    "needs_lawyer": True,
    "urgency": "normal",
    "summary_for_lawyer": "[IA de teste] Mensagem recebida; triagem simulada.",
    "reply": (
        "Obrigado pela mensagem! Vou encaminhar para o(a) advogado(a) responsável, "
        "que vai te responder em breve."
    ),
}


@dataclass
class FakeLlmClient:
    provider: str = "fake"
    # Respostas (ou erros) programadas para as próximas chamadas, em ordem.
    queue: list[dict[str, Any] | LlmError] = field(default_factory=list)
    calls: list[LlmRequest] = field(default_factory=list)

    def complete(self, request: LlmRequest) -> LlmResult:
        self.calls.append(request)
        item: dict[str, Any] | LlmError = self.queue.pop(0) if self.queue else DEFAULT_TRIAGE
        if isinstance(item, LlmError):
            raise item
        return LlmResult(
            data=dict(item),
            raw_text=json.dumps(item, ensure_ascii=False),
            provider=self.provider,
            model="fake-triage-1",
        )

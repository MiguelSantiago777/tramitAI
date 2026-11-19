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


DEFAULT_MOVEMENT_UPDATE: dict[str, Any] = {
    "message": (
        "[IA de teste] O tribunal registrou um novo andamento no seu processo. "
        "O(a) advogado(a) está acompanhando. Se tiver dúvida, é só responder."
    ),
    "client_relevant": True,
    "needs_lawyer": True,
    "summary_for_lawyer": "[IA de teste] Andamento novo; texto simulado.",
}
DEFAULT_LEGAL_DRAFT: dict[str, Any] = {
    "title": "Minuta de teste",
    "body": (
        "# PROCURAÇÃO AD JUDICIA\n\n"
        "## OUTORGANTE\n\n"
        "[NOME DO CLIENTE], inscrito(a) no CPF/CNPJ sob o nº [CPF/CNPJ DO CLIENTE], "
        "residente em [ENDEREÇO DO CLIENTE].\n\n"
        "## OUTORGADO\n\n"
        "[NOME DO ADVOGADO], OAB [OAB DO ADVOGADO], do escritório [NOME DO ESCRITÓRIO].\n\n"
        "> [DATA DE HOJE]"
    ),
    "review_notes": "[IA de teste] Confira o endereço do cliente.",
}
_DEFAULTS = {"movement_update": DEFAULT_MOVEMENT_UPDATE, "legal_draft": DEFAULT_LEGAL_DRAFT}


@dataclass
class FakeLlmClient:
    provider: str = "fake"
    # Respostas (ou erros) programadas para as próximas chamadas, em ordem.
    queue: list[dict[str, Any] | LlmError] = field(default_factory=list)
    calls: list[LlmRequest] = field(default_factory=list)

    def complete(self, request: LlmRequest) -> LlmResult:
        self.calls.append(request)
        default = _DEFAULTS.get(request.purpose, DEFAULT_TRIAGE)
        item: dict[str, Any] | LlmError = self.queue.pop(0) if self.queue else default
        if isinstance(item, LlmError):
            raise item
        return LlmResult(
            data=dict(item),
            raw_text=json.dumps(item, ensure_ascii=False),
            provider=self.provider,
            model="fake-llm-1",
        )

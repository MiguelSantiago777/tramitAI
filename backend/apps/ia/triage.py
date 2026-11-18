"""Contrato da triagem: JSON Schema enviado ao LLM e validação defensiva da resposta."""

from dataclasses import dataclass
from typing import Any

INTENTS = ["case_status", "new_matter", "documents", "scheduling", "fees", "greeting", "other"]
URGENCIES = ["low", "normal", "high"]
MAX_REPLY_LENGTH = 1500

TRIAGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": INTENTS},
        "needs_lawyer": {"type": "boolean"},
        "triage_complete": {"type": "boolean"},
        # Agenda: "offer" = ofereceu horários; "book" = contato escolheu (slot + modo).
        "scheduling_step": {"type": "string", "enum": ["none", "offer", "book"]},
        "booking_slot": {"type": "string"},
        "booking_mode": {"type": "string", "enum": ["", "presencial", "online"]},
        "urgency": {"type": "string", "enum": URGENCIES},
        "summary_for_lawyer": {"type": "string"},
        "reply": {"type": "string"},
    },
    "required": [
        "intent",
        "needs_lawyer",
        "triage_complete",
        "scheduling_step",
        "booking_slot",
        "booking_mode",
        "urgency",
        "summary_for_lawyer",
        "reply",
    ],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class TriageResult:
    intent: str
    needs_lawyer: bool
    urgency: str
    summary_for_lawyer: str
    reply: str
    # Triagem de contato novo terminou (já tem nome e resumo): vai para o advogado.
    triage_complete: bool = True
    scheduling_step: str = "none"
    booking_slot: str = ""
    booking_mode: str = ""


class InvalidTriage(ValueError):
    pass


def parse_triage(data: dict[str, Any]) -> TriageResult:
    """Valida mesmo com saída estruturada: provedor trocável não garante o schema."""
    try:
        intent = str(data["intent"])
        urgency = str(data["urgency"])
        needs_lawyer = data["needs_lawyer"]
        summary = str(data["summary_for_lawyer"]).strip()
        reply = str(data["reply"]).strip()
    except (KeyError, TypeError) as exc:
        raise InvalidTriage("campos ausentes") from exc
    if not isinstance(needs_lawyer, bool):
        raise InvalidTriage("needs_lawyer não é booleano")
    # Ausente ou inválido = "terminou": o caminho seguro é a aprovação do advogado.
    triage_complete = data.get("triage_complete", True)
    if not isinstance(triage_complete, bool):
        triage_complete = True
    step = str(data.get("scheduling_step") or "none")
    if not reply:
        raise InvalidTriage("resposta vazia")
    return TriageResult(
        intent=intent if intent in INTENTS else "other",
        needs_lawyer=needs_lawyer,
        urgency=urgency if urgency in URGENCIES else "normal",
        summary_for_lawyer=summary[:1000],
        reply=reply[:MAX_REPLY_LENGTH],
        triage_complete=triage_complete,
        scheduling_step=step if step in ("offer", "book") else "none",
        booking_slot=str(data.get("booking_slot") or "")[:8],
        booking_mode=str(data.get("booking_mode") or "")[:12],
    )

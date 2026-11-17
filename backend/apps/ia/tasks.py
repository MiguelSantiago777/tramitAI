import uuid
from typing import Any

from celery import shared_task

from . import movements, services


@shared_task(bind=True, max_retries=3, acks_late=True)
def triage_message(self: Any, tenant_id: str, conversation_id: str, message_id: str) -> str:
    """Triagem de uma mensagem recebida. Idempotente o bastante: rascunho novo substitui o
    pendente da conversa, e cada tentativa fica registrada em AiGeneration."""
    try:
        return services.handle_inbound(
            uuid.UUID(tenant_id), uuid.UUID(conversation_id), uuid.UUID(message_id)
        )
    except services.RetryableTriageError as exc:
        raise self.retry(exc=exc, countdown=min(30 * 2**self.request.retries, 600)) from exc


@shared_task(bind=True, max_retries=3, acks_late=True)
def explain_movements(self: Any, tenant_id: str, case_id: str) -> str:
    """Rascunho de aviso dos andamentos novos de um processo (um por cliente vinculado)."""
    try:
        return movements.explain_case_movements(uuid.UUID(tenant_id), uuid.UUID(case_id))
    except movements.RetryableMovementError as exc:
        raise self.retry(exc=exc, countdown=min(60 * 2**self.request.retries, 900)) from exc

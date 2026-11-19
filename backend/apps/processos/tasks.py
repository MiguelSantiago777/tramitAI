import uuid
from typing import Any

from celery import shared_task

from . import monitoring, publications


@shared_task(bind=True, max_retries=6, acks_late=True)
def sync_case_task(self: Any, tenant_id: str, case_id: str) -> str:
    """Consulta o andamento de um processo. Idempotente (dedupe por fingerprint + lock).

    DataJud cheio (429/timeout): tenta de novo em 1, 2, 4, 8, 16 e 30 min (~1 h no total).
    """
    try:
        return monitoring.sync_case(uuid.UUID(tenant_id), uuid.UUID(case_id))
    except monitoring.RetryableSyncError as exc:
        if self.request.retries >= self.max_retries:
            return f"gave_up:{exc}"
        raise self.retry(exc=exc, countdown=min(60 * 2**self.request.retries, 1800)) from exc


@shared_task
def schedule_case_checks() -> int:
    return monitoring.schedule_due_checks()


@shared_task(bind=True, max_retries=4, acks_late=True)
def sync_oab_task(self: Any, tenant_id: str, oab_id: str) -> str:
    """Busca as publicações do Diário de uma OAB. Idempotente (dedupe pelo id do DJEN)."""
    try:
        return publications.sync_oab(uuid.UUID(tenant_id), uuid.UUID(oab_id))
    except monitoring.RetryableSyncError as exc:
        raise self.retry(exc=exc, countdown=min(120 * 2**self.request.retries, 3600)) from exc


@shared_task
def schedule_publication_checks() -> int:
    return publications.schedule_due_checks()

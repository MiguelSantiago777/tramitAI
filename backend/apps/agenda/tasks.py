import logging
import uuid
from typing import Any

from celery import shared_task

from apps.core.tenancy import tenant_atomic

from . import services

logger = logging.getLogger(__name__)


@shared_task
def create_event_reminders() -> int:
    return services.create_event_reminders()


@shared_task(bind=True, max_retries=5, acks_late=True)
def sync_event_to_google(self: Any, tenant_id: str, event_id: str) -> str:
    from . import google

    try:
        return google.sync_event(uuid.UUID(tenant_id), uuid.UUID(event_id))
    except google.GoogleError as exc:
        if not exc.retryable or self.request.retries >= self.max_retries:
            return f"failed_{exc.code}"
        raise self.retry(exc=exc, countdown=min(30 * 2**self.request.retries, 900)) from exc


@shared_task
def refresh_google_busy() -> int:
    """Beat: atualiza o livre/ocupado do Google de quem conectou (todos os escritórios)."""
    from apps.tenants.models import Tenant

    from . import google
    from .models import GoogleCalendarConnection

    done = 0
    for tenant_id in Tenant.objects.filter(status=Tenant.Status.ACTIVE).values_list(
        "id", flat=True
    ):
        with tenant_atomic(tenant_id):
            ids = list(
                GoogleCalendarConnection.objects.filter(needs_reconnect=False).values_list(
                    "id", flat=True
                )
            )
        for connection_id in ids:
            try:
                google.refresh_busy(tenant_id, connection_id)
                done += 1
            except google.GoogleError as exc:
                logger.info("google: ocupado não atualizado (%s)", exc.code)
    return done

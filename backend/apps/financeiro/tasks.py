import logging
import uuid
from typing import Any

from celery import shared_task

from apps.core.mercadopago import MercadoPagoError

from . import services

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=8, acks_late=True)
def sync_payment_task(self: Any, tenant_id: str, payment_id: str) -> str:
    """Aviso do Mercado Pago: consulta o pagamento e dá baixa. Repete se o MP não responder."""
    try:
        return services.sync_payment(uuid.UUID(tenant_id), payment_id)
    except MercadoPagoError as exc:
        if self.request.retries >= self.max_retries:
            logger.warning("mercadopago: desistindo de consultar pagamento (%s)", exc.code)
            return "gave_up"
        raise self.retry(exc=exc, countdown=min(30 * 2**self.request.retries, 3600)) from exc


@shared_task
def create_payment_reminders() -> int:
    return services.create_payment_reminders()

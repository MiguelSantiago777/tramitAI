import logging
from typing import Any

from celery import shared_task

from apps.core.mercadopago import MercadoPagoError

from . import services

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=8, acks_late=True)
def sync_subscription_event(self: Any, kind: str, object_id: str) -> str:
    try:
        if kind == "subscription_authorized_payment":
            return services.sync_from_authorized_payment(object_id)
        return services.sync_subscription(object_id)
    except MercadoPagoError as exc:
        if not exc.retryable or self.request.retries >= self.max_retries:
            logger.warning("assinatura: aviso não processado (%s)", exc.code)
            return "failed"
        raise self.retry(exc=exc, countdown=min(30 * 2**self.request.retries, 3600)) from exc


@shared_task
def refresh_subscriptions() -> int:
    return services.refresh_all()

import logging
import uuid
from typing import Any

from celery import shared_task

from . import services

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=6,
    acks_late=True,
)
def process_inbound_event(self: Any, event_id: int) -> None:
    """Processa um evento do webhook. Idempotente: pode rodar mais de uma vez."""
    try:
        services.process_event(event_id)
    except Exception as exc:
        services.record_event_failure(event_id, exc)
        logger.warning("whatsapp: falha ao processar evento %s (%s)", event_id, type(exc).__name__)
        raise


@shared_task(bind=True, max_retries=5, acks_late=True)
def send_message(self: Any, tenant_id: str, message_id: str) -> None:
    """Envia uma mensagem de saída. Só tenta de novo quando é certo que nada saiu."""
    tid, mid = uuid.UUID(tenant_id), uuid.UUID(message_id)
    try:
        services.deliver_outbound(tid, mid)
    except services.RetryableSendError as exc:
        if self.request.retries >= self.max_retries:
            services.give_up_sending(tid, mid)
            return
        raise self.retry(exc=exc, countdown=min(5 * 2**self.request.retries, 300)) from exc


@shared_task
def purge_processed_webhook_events() -> int:
    return services.purge_processed_events()


@shared_task
def fail_stuck_outbound_messages() -> int:
    return services.fail_stuck_sending()


@shared_task(bind=True, max_retries=3, acks_late=True)
def alert_whatsapp_disconnected(self: Any, tenant_id: str) -> int:
    """Avisa os titulares por e-mail: o WhatsApp foi desconectado e precisa de novo QR."""
    from django.conf import settings
    from django.core.mail import send_mail

    from apps.accounts.models import Membership
    from apps.tenants.models import Tenant

    tenant = Tenant.objects.filter(pk=tenant_id).first()
    if tenant is None:
        return 0
    emails = list(
        Membership.objects.filter(
            tenant_id=tenant_id, role=Membership.Role.OWNER, is_active=True, user__is_active=True
        ).values_list("user__email", flat=True)
    )
    if not emails:
        return 0
    link = f"{settings.FRONTEND_URL.rstrip('/')}/configuracoes/whatsapp"
    try:
        send_mail(
            subject="TramitAI: o WhatsApp do escritório foi desconectado",
            message=(
                f"O WhatsApp do {tenant.name} foi desconectado do TramitAI (pelo celular ou pelo "
                "próprio WhatsApp). Enquanto isso, as mensagens dos clientes não chegam ao "
                "sistema.\n\n"
                f"Para conectar de novo, abra {link} e leia o QR Code com o celular do "
                "escritório.\n"
            ),
            from_email=None,
            recipient_list=emails,
        )
    except Exception as exc:
        logger.warning("alerta whatsapp: falha no envio (%s)", type(exc).__name__)
        raise self.retry(exc=exc, countdown=120) from exc
    return len(emails)

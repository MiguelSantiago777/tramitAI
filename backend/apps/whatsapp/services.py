"""Regras do WhatsApp: ingestão do webhook, status e envio manual.

Regras que valem aqui:
- Nada de conteúdo de mensagem em log (só ids técnicos e contagens).
- Chamada à Meta sempre FORA de transação (deliver_outbound).
- Nunca reenviar sozinho quando não dá para saber se a Meta aceitou.
"""

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import DateTimeField, F, Value
from django.db.models.functions import Coalesce, Greatest
from django.utils import timezone
from rest_framework import status as http_status

from apps.accounts.models import User
from apps.clientes.models import Client
from apps.core.br import whatsapp_phone_candidates
from apps.core.crypto import decrypt_secret, encrypt_secret
from apps.core.exceptions import ApiError
from apps.core.tenancy import tenant_atomic, tenant_context
from apps.tenants.models import Tenant

from .gateway import Credentials, GatewayError, get_gateway
from .inbound import InboundMessage, StatusUpdate, parse_payload
from .models import (
    OUTBOUND_STATUS_RANK,
    Conversation,
    InboundWebhookEvent,
    Message,
    PhoneNumberRoute,
    WhatsAppAccount,
)

logger = logging.getLogger(__name__)

SERVICE_WINDOW = timedelta(hours=24)
MAX_TEXT_LENGTH = 4096  # limite da Cloud API para mensagem de texto
STUCK_SENDING_AFTER = timedelta(minutes=5)


class RetryableSendError(Exception):
    """A mensagem comprovadamente não saiu; a task pode tentar de novo."""


# ============================================================================ contas


def register_account(
    *,
    tenant: Tenant,
    phone_number_id: str,
    waba_id: str,
    display_phone: str,
    access_token: str,
) -> WhatsAppAccount:
    """Onboarding manual do piloto: conta (com token cifrado) + rota do webhook."""
    with tenant_atomic(tenant.id):
        account = WhatsAppAccount.objects.create(
            phone_number_id=phone_number_id,
            waba_id=waba_id,
            display_phone=display_phone,
            access_token_encrypted=encrypt_secret(access_token),
        )
        PhoneNumberRoute.objects.create(phone_number_id=phone_number_id, tenant=tenant)
    return account


# ============================================================================ webhook (entrada)


def store_inbound_event(payload: dict[str, Any]) -> InboundWebhookEvent:
    """Grava o payload bruto e agenda o processamento para depois do commit."""
    from .tasks import process_inbound_event

    event = InboundWebhookEvent.objects.create(payload=payload)
    transaction.on_commit(lambda: process_inbound_event.delay(event.id))
    return event


def process_event(event_id: int) -> None:
    """Processa um evento do webhook. Idempotente: evento já processado é ignorado e cada
    mensagem é deduplicada pelo wamid (constraint unique)."""
    with transaction.atomic():
        event = InboundWebhookEvent.objects.select_for_update().filter(pk=event_id).first()
        if event is None or event.processed_at is not None:
            return

        messages, statuses = parse_payload(event.payload)
        by_number: dict[str, tuple[list[InboundMessage], list[StatusUpdate]]] = defaultdict(
            lambda: ([], [])
        )
        for m in messages:
            by_number[m.phone_number_id][0].append(m)
        for s in statuses:
            by_number[s.phone_number_id][1].append(s)

        for phone_number_id, (msgs, sts) in by_number.items():
            route = PhoneNumberRoute.objects.filter(phone_number_id=phone_number_id).first()
            if route is None:
                logger.warning("whatsapp webhook: phone_number_id sem rota (evento %s)", event_id)
                continue
            with tenant_context(route.tenant_id):
                created = sum(1 for m in msgs if ingest_message(m) is not None)
                for s in sts:
                    apply_status(s)
            logger.info(
                "whatsapp webhook: evento %s tenant %s: %s mensagens novas, %s status",
                event_id,
                route.tenant_id,
                created,
                len(sts),
            )

        event.processed_at = timezone.now()
        event.attempts = F("attempts") + 1
        event.last_error = ""
        event.save(update_fields=["processed_at", "attempts", "last_error"])


def record_event_failure(event_id: int, exc: BaseException) -> None:
    # Só o tipo da exceção: a mensagem pode carregar conteúdo do payload.
    InboundWebhookEvent.objects.filter(pk=event_id).update(
        attempts=F("attempts") + 1, last_error=type(exc).__name__
    )


def ingest_message(m: InboundMessage) -> Message | None:
    """Grava uma mensagem recebida (tenant já ativo). Devolve None se já existia."""
    account = WhatsAppAccount.objects.filter(phone_number_id=m.phone_number_id).first()
    if account is None:
        logger.warning("whatsapp webhook: rota sem conta ativa")
        return None
    if Message.objects.filter(wa_message_id=m.wa_message_id).exists():
        return None

    conversation, _ = Conversation.objects.get_or_create(
        account=account, wa_id=m.wa_id, defaults={"contact_name": m.contact_name}
    )
    try:
        with transaction.atomic():
            message = Message.objects.create(
                conversation=conversation,
                direction=Message.Direction.INBOUND,
                wa_message_id=m.wa_message_id,
                type=m.type,
                body=m.body,
                media_id=m.media_id,
                status=Message.Status.RECEIVED,
                wa_timestamp=m.timestamp,
            )
    except IntegrityError:
        return None  # corrida com outro worker processando o mesmo wamid

    updates: dict[str, Any] = {
        "unread_count": F("unread_count") + 1,
        "status": Conversation.Status.OPEN,
        # Greatest no SQL: dois workers gravando a mesma conversa não regridem a data.
        "last_message_at": _greatest("last_message_at", m.timestamp),
        "last_inbound_at": _greatest("last_inbound_at", m.timestamp),
    }
    if m.contact_name and m.contact_name != conversation.contact_name:
        updates["contact_name"] = m.contact_name
    if conversation.client_id is None:
        client = match_client(m.wa_id)
        if client is not None:
            updates["client"] = client
    Conversation.objects.filter(pk=conversation.pk).update(**updates)
    return message


def _greatest(field: str, value: datetime) -> Greatest:
    ts = Value(value, output_field=DateTimeField())
    return Greatest(Coalesce(F(field), ts), ts)


def match_client(wa_id: str) -> Client | None:
    """Cliente com esse telefone (com/sem nono dígito). Só vincula se houver exatamente um."""
    matches = list(
        Client.objects.filter(phone_e164__in=whatsapp_phone_candidates(wa_id))
        .exclude(status=Client.Status.ARCHIVED)
        .order_by()[:2]
    )
    return matches[0] if len(matches) == 1 else None


def apply_status(s: StatusUpdate) -> None:
    """Atualiza o status de uma mensagem enviada. Nunca regride (webhooks chegam fora de ordem)."""
    message = Message.objects.filter(
        wa_message_id=s.wa_message_id, direction=Message.Direction.OUTBOUND
    ).first()
    if message is None:
        return

    if s.status == "failed":
        if message.status != Message.Status.READ:
            message.status = Message.Status.FAILED
            message.error_code = s.error_code
            message.error_detail = s.error_detail
            message.save(update_fields=["status", "error_code", "error_detail", "updated_at"])
        return

    new_status = {
        "sent": Message.Status.SENT,
        "delivered": Message.Status.DELIVERED,
        "read": Message.Status.READ,
    }.get(s.status)
    if new_status is None:
        return
    fields = []
    if new_status in (Message.Status.DELIVERED, Message.Status.READ) and not message.delivered_at:
        message.delivered_at = s.timestamp
        fields.append("delivered_at")
    if new_status == Message.Status.READ and not message.read_at:
        message.read_at = s.timestamp
        fields.append("read_at")
    current_rank = OUTBOUND_STATUS_RANK.get(message.status, -1)
    if OUTBOUND_STATUS_RANK[new_status] > current_rank and message.status != Message.Status.FAILED:
        message.status = new_status
        fields.append("status")
    if fields:
        message.save(update_fields=[*fields, "updated_at"])


# ============================================================================ envio manual


def window_open(conversation: Conversation, *, now: datetime | None = None) -> bool:
    if conversation.last_inbound_at is None:
        return False
    return (now or timezone.now()) - conversation.last_inbound_at < SERVICE_WINDOW


def window_expires_at(conversation: Conversation) -> datetime | None:
    if conversation.last_inbound_at is None:
        return None
    return conversation.last_inbound_at + SERVICE_WINDOW


def send_text_reply(*, conversation: Conversation, body: str, user: User) -> Message:
    """Resposta manual do escritório. Grava QUEUED e agenda o envio depois do commit."""
    from .tasks import send_message

    body = body.strip()
    if not body:
        raise ApiError("Escreva a mensagem.", code="empty_message")
    if len(body) > MAX_TEXT_LENGTH:
        raise ApiError(
            f"Mensagem longa demais (máx. {MAX_TEXT_LENGTH} caracteres).", code="message_too_long"
        )
    if not window_open(conversation):
        raise ApiError(
            "A janela de 24h do WhatsApp está fechada: o cliente não manda mensagem há mais de "
            "24 horas. Só é possível enviar um modelo aprovado pela Meta.",
            code="window_closed",
            status_code=http_status.HTTP_409_CONFLICT,
        )

    message = Message.objects.create(
        conversation=conversation,
        direction=Message.Direction.OUTBOUND,
        type=Message.Type.TEXT,
        body=body,
        status=Message.Status.QUEUED,
        sent_by=user,
    )
    Conversation.objects.filter(pk=conversation.pk).update(
        last_message_at=message.created_at, unread_count=0
    )
    tenant_id, message_id = str(conversation.tenant_id), str(message.id)
    transaction.on_commit(lambda: send_message.delay(tenant_id, message_id))
    return message


def deliver_outbound(tenant_id: uuid.UUID, message_id: uuid.UUID) -> None:
    """Envia uma mensagem QUEUED. Três transações curtas; a chamada HTTP fica fora delas."""
    with tenant_atomic(tenant_id):
        message = (
            Message.objects.select_for_update()
            .select_related("conversation__account")
            .filter(pk=message_id, direction=Message.Direction.OUTBOUND)
            .first()
        )
        if message is None or message.status != Message.Status.QUEUED:
            return  # já tratada (task duplicada ou reentregue)
        message.status = Message.Status.SENDING
        message.save(update_fields=["status", "updated_at"])
        account = message.conversation.account
        credentials = Credentials(
            phone_number_id=account.phone_number_id,
            access_token=decrypt_secret(account.access_token_encrypted),
        )
        to, body = message.conversation.wa_id, message.body

    try:
        result = get_gateway().send_text(credentials, to=to, body=body)
    except GatewayError as exc:
        with tenant_atomic(tenant_id):
            Message.objects.filter(pk=message_id).update(
                status=Message.Status.QUEUED if exc.retryable else Message.Status.FAILED,
                error_code=exc.code,
                error_detail=_failure_text(exc),
            )
        if exc.retryable:
            raise RetryableSendError(exc.code) from exc
        return

    with tenant_atomic(tenant_id):
        Message.objects.filter(pk=message_id, status=Message.Status.SENDING).update(
            status=Message.Status.SENT,
            wa_message_id=result.wa_message_id,
            wa_timestamp=timezone.now(),
            error_code="",
            error_detail="",
        )


def _failure_text(exc: GatewayError) -> str:
    if exc.code == "uncertain":
        return "Envio não confirmado pela Meta. Verifique no WhatsApp antes de reenviar."
    return exc.detail


def give_up_sending(tenant_id: uuid.UUID, message_id: uuid.UUID) -> None:
    with tenant_atomic(tenant_id):
        Message.objects.filter(pk=message_id, status=Message.Status.QUEUED).update(
            status=Message.Status.FAILED,
            error_detail="Não foi possível enviar depois de várias tentativas.",
        )


def fail_stuck_sending() -> int:
    """Mensagens presas em SENDING (worker morreu no meio): marca FAILED para revisão humana."""
    limit = timezone.now() - STUCK_SENDING_AFTER
    total = 0
    for tenant_id in Tenant.objects.values_list("id", flat=True):
        with tenant_atomic(tenant_id):
            total += Message.objects.filter(
                status=Message.Status.SENDING, updated_at__lt=limit
            ).update(
                status=Message.Status.FAILED,
                error_code="uncertain",
                error_detail="Envio não confirmado. Verifique no WhatsApp antes de reenviar.",
            )
    return total


def purge_processed_events() -> int:
    limit = timezone.now() - timedelta(days=settings.WEBHOOK_EVENT_RETENTION_DAYS)
    deleted, _ = InboundWebhookEvent.objects.filter(processed_at__lt=limit).delete()
    return deleted


def mark_read(conversation: Conversation) -> None:
    Conversation.objects.filter(pk=conversation.pk).update(unread_count=0)

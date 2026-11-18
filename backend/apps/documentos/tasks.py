"""Guarda a mídia recebida no WhatsApp como documento.

Três fases (regra do projeto: nada de HTTP com transação aberta):
1. transação curta: lê a mensagem e as credenciais;
2. fora de transação: baixa do provedor (Meta ou ponte);
3. transação curta: grava o documento. Depois, avisa a ponte que pode apagar a cópia.
"""

import logging
import uuid
from typing import Any

from celery import shared_task

from apps.core.tenancy import tenant_atomic
from apps.whatsapp.gateway import GatewayError, get_gateway
from apps.whatsapp.models import Message
from apps.whatsapp.services import account_credentials

from . import services
from .models import Document

logger = logging.getLogger(__name__)

MEDIA_TYPES = {
    Message.Type.IMAGE,
    Message.Type.AUDIO,
    Message.Type.VIDEO,
    Message.Type.DOCUMENT,
}


class RetryableMediaError(Exception):
    pass


def store_message_media(tenant_id: uuid.UUID, message_id: uuid.UUID) -> str:
    with tenant_atomic(tenant_id):
        message = (
            Message.objects.select_related("conversation__account")
            .filter(pk=message_id, direction=Message.Direction.INBOUND)
            .first()
        )
        if message is None or not message.media_id or message.error_code:
            return "skipped"
        if Document.objects.filter(message=message).exists():
            return "exists"
        account = message.conversation.account
        provider, media_id = account.provider, message.media_id
        credentials = account_credentials(account)

    gateway = get_gateway(provider)
    try:
        media = gateway.download_media(credentials, media_id=media_id)
    except GatewayError as exc:
        if exc.retryable:
            raise RetryableMediaError(exc.code) from exc
        with tenant_atomic(tenant_id):
            Message.objects.filter(pk=message_id).update(
                error_code=exc.code[:32],
                error_detail="Não foi possível guardar o arquivo. Peça para o contato reenviar.",
            )
        logger.warning("mídia: falha definitiva (%s) mensagem %s", exc.code, message_id)
        return "failed"

    with tenant_atomic(tenant_id):
        message = Message.objects.select_related("conversation").get(pk=message_id)
        if not Document.objects.filter(message=message).exists():
            services.create_from_whatsapp(
                message=message,
                content=media.content,
                content_type=media.content_type,
                filename=media.filename or message.media_filename,
            )
    gateway.release_media(credentials, media_id=media_id)
    return "stored"


@shared_task(bind=True, max_retries=6, acks_late=True)
def store_message_media_task(self: Any, tenant_id: str, message_id: str) -> str:
    try:
        return store_message_media(uuid.UUID(tenant_id), uuid.UUID(message_id))
    except RetryableMediaError as exc:
        if self.request.retries >= self.max_retries:
            logger.warning("mídia: desistindo depois de %s tentativas", self.request.retries)
            return "gave_up"
        raise self.retry(exc=exc, countdown=min(10 * 2**self.request.retries, 600)) from exc

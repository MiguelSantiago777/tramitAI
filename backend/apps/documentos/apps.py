from typing import Any

from django.apps import AppConfig
from django.db import transaction


def _schedule_media(sender: Any, message: Any, conversation: Any, **kwargs: Any) -> None:
    from .tasks import MEDIA_TYPES, store_message_media_task

    if message.type not in MEDIA_TYPES or not message.media_id or message.error_code:
        return
    args = (str(message.tenant_id), str(message.pk))
    transaction.on_commit(lambda: store_message_media_task.delay(*args))


class DocumentosConfig(AppConfig):
    name = "apps.documentos"
    verbose_name = "Documentos"

    def ready(self) -> None:
        from apps.whatsapp.signals import inbound_message_received

        inbound_message_received.connect(_schedule_media, dispatch_uid="documentos.media")

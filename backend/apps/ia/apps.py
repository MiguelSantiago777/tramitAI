from typing import Any

from django.apps import AppConfig
from django.conf import settings
from django.db import transaction


def _schedule_triage(sender: Any, message: Any, conversation: Any, **kwargs: Any) -> None:
    from .tasks import triage_message

    args = [str(conversation.tenant_id), str(conversation.pk), str(message.pk)]
    transaction.on_commit(
        lambda: triage_message.apply_async(args=args, countdown=settings.TRIAGE_DEBOUNCE_SECONDS)
    )


def _schedule_movement_update(sender: Any, case: Any, **kwargs: Any) -> None:
    from .tasks import explain_movements

    args = [str(case.tenant_id), str(case.pk)]
    transaction.on_commit(lambda: explain_movements.apply_async(args=args))


class IaConfig(AppConfig):
    name = "apps.ia"
    verbose_name = "Inteligência artificial"

    def ready(self) -> None:
        from apps.whatsapp.signals import inbound_message_received

        inbound_message_received.connect(_schedule_triage, dispatch_uid="ia.schedule_triage")

        from apps.processos.signals import movements_detected

        movements_detected.connect(
            _schedule_movement_update, dispatch_uid="ia.schedule_movement_update"
        )

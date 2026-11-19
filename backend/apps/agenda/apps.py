from typing import Any

from django.apps import AppConfig


def _movements_detected(sender: Any, case: Any, **kwargs: Any) -> None:
    from .services import create_tasks_for_movements

    create_tasks_for_movements(case)


def _publications_detected(sender: Any, publications: Any, **kwargs: Any) -> None:
    from .services import create_tasks_for_publications

    create_tasks_for_publications(publications)


def _event_saved(sender: Any, instance: Any, **kwargs: Any) -> None:
    """Compromisso mudou: reflete no Google do responsável (a task confere se conectou)."""
    from django.db import transaction

    from .tasks import sync_event_to_google

    if not instance.responsible_id:
        return
    args = (str(instance.tenant_id), str(instance.pk))
    transaction.on_commit(lambda: sync_event_to_google.delay(*args))


class AgendaConfig(AppConfig):
    name = "apps.agenda"
    verbose_name = "Agenda e tarefas"

    def ready(self) -> None:
        from django.db.models.signals import post_save

        from apps.processos.signals import movements_detected, publications_detected

        from .models import Event

        movements_detected.connect(_movements_detected, dispatch_uid="agenda.movement_tasks")
        publications_detected.connect(
            _publications_detected, dispatch_uid="agenda.publication_tasks"
        )
        post_save.connect(_event_saved, sender=Event, dispatch_uid="agenda.google_sync")

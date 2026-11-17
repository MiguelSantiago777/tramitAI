from typing import Any

from django.apps import AppConfig


def _movements_detected(sender: Any, case: Any, **kwargs: Any) -> None:
    from .services import create_tasks_for_movements

    create_tasks_for_movements(case)


class AgendaConfig(AppConfig):
    name = "apps.agenda"
    verbose_name = "Agenda e tarefas"

    def ready(self) -> None:
        from apps.processos.signals import movements_detected

        movements_detected.connect(_movements_detected, dispatch_uid="agenda.movement_tasks")

from typing import Any

from django.apps import AppConfig


def _on_message_settled(sender: Any, message: Any, **kwargs: Any) -> None:
    from .services import on_message_settled

    on_message_settled(message)


class AprovacoesConfig(AppConfig):
    name = "apps.aprovacoes"
    verbose_name = "Aprovações"

    def ready(self) -> None:
        from apps.whatsapp.signals import outbound_message_settled

        outbound_message_settled.connect(
            _on_message_settled, dispatch_uid="aprovacoes.on_message_settled"
        )

from typing import Any

from django.apps import AppConfig


def _on_message_settled(sender: Any, message: Any, **kwargs: Any) -> None:
    from .services import on_message_settled

    on_message_settled(message)


def _on_inbound(sender: Any, message: Any, conversation: Any, **kwargs: Any) -> None:
    from .services import on_inbound_message

    on_inbound_message(conversation)


class AprovacoesConfig(AppConfig):
    name = "apps.aprovacoes"
    verbose_name = "Aprovações"

    def ready(self) -> None:
        from apps.whatsapp.signals import inbound_message_received, outbound_message_settled

        outbound_message_settled.connect(
            _on_message_settled, dispatch_uid="aprovacoes.on_message_settled"
        )
        inbound_message_received.connect(_on_inbound, dispatch_uid="aprovacoes.on_inbound")

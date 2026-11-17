from functools import cache

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .base import Credentials, GatewayError, SendResult, WhatsAppGateway
from .fake import FakeGateway

__all__ = ["Credentials", "FakeGateway", "GatewayError", "SendResult", "get_gateway"]


@cache
def _build(name: str) -> WhatsAppGateway:
    if name == "fake":
        return FakeGateway()
    if name == "cloud_api":
        from .cloud_api import CloudApiGateway

        return CloudApiGateway()
    raise ImproperlyConfigured(f"WHATSAPP_GATEWAY desconhecido: {name}")


def get_gateway() -> WhatsAppGateway:
    return _build(settings.WHATSAPP_GATEWAY)

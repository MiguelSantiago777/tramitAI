from functools import cache

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .base import Credentials, GatewayError, SendResult, WhatsAppGateway
from .fake import FakeGateway

__all__ = ["Credentials", "FakeGateway", "GatewayError", "SendResult", "get_gateway"]

CLOUD_API = "CLOUD_API"
BAILEYS = "BAILEYS"


@cache
def _build(name: str) -> WhatsAppGateway:
    if name == "fake":
        return _fake()
    if name == "cloud_api":
        from .cloud_api import CloudApiGateway

        return CloudApiGateway()
    if name == "bridge":
        from .bridge import BridgeGateway

        return BridgeGateway()
    raise ImproperlyConfigured(f"gateway de WhatsApp desconhecido: {name}")


@cache
def _fake() -> FakeGateway:
    # Um só fake para os dois provedores: os testes inspecionam o que "saiu".
    return FakeGateway()


def get_gateway(provider: str = CLOUD_API) -> WhatsAppGateway:
    """Gateway do provedor da conta (Cloud API da Meta ou ponte Baileys)."""
    if provider == BAILEYS:
        return _build(settings.WHATSAPP_BAILEYS_GATEWAY)
    return _build(settings.WHATSAPP_GATEWAY)

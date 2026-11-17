"""Webhook da Meta. A view só valida, grava o bruto e agenda a task; o resto é no worker."""

import hmac
import json
import logging

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from . import services
from .signature import is_valid_signature

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class WhatsAppWebhookView(View):
    http_method_names = ["get", "post"]

    def get(self, request: HttpRequest) -> HttpResponse:
        """Verificação do endpoint pela Meta (hub.challenge)."""
        token = request.GET.get("hub.verify_token", "")
        expected = settings.WHATSAPP_VERIFY_TOKEN
        if (
            request.GET.get("hub.mode") == "subscribe"
            and expected
            and hmac.compare_digest(token, expected)
        ):
            return HttpResponse(request.GET.get("hub.challenge", ""), content_type="text/plain")
        return HttpResponse(status=403)

    def post(self, request: HttpRequest) -> HttpResponse:
        signature = request.headers.get("X-Hub-Signature-256")
        if not is_valid_signature(request.body, signature, settings.WHATSAPP_APP_SECRET):
            logger.warning("whatsapp webhook: assinatura inválida ou ausente")
            return HttpResponse(status=401)
        try:
            payload = json.loads(request.body)
        except ValueError:
            return HttpResponse(status=400)
        if not isinstance(payload, dict):
            return HttpResponse(status=400)

        services.store_inbound_event(payload)
        # 200 rápido: a Meta reenvia se demorar ou falhar. Processamento é idempotente.
        return HttpResponse(status=200)

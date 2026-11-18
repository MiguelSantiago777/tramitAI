"""Aviso do Mercado Pago (notification_url de cada cobrança do escritório).

O aviso não é confiável por si: só dizemos "olhe o pagamento X". A task consulta o pagamento
na API do MP com o token do escritório e só então dá baixa. Por isso não há assinatura aqui:
um aviso falso só faz a gente consultar um pagamento que não existe (ou não é aprovado).
"""

import json
import logging
import re

from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from . import services

logger = logging.getLogger(__name__)
_PAYMENT_ID = re.compile(r"^\d{1,20}$")


def payment_id_from(request: HttpRequest) -> str | None:
    """Aceita os dois formatos do MP: Webhooks (type/data.id) e IPN (topic/id)."""
    kind = request.GET.get("type") or request.GET.get("topic") or ""
    payment_id = request.GET.get("data.id") or request.GET.get("id") or ""
    if request.body:
        try:
            body = json.loads(request.body)
        except ValueError:
            body = {}
        if isinstance(body, dict):
            kind = str(body.get("type") or body.get("topic") or kind)
            data = body.get("data")
            if isinstance(data, dict) and data.get("id"):
                payment_id = str(data["id"])
    if kind != "payment" or not _PAYMENT_ID.match(payment_id):
        return None
    return payment_id


@method_decorator(csrf_exempt, name="dispatch")
class MercadoPagoWebhookView(View):
    http_method_names = ["post"]

    def post(self, request: HttpRequest, token: str) -> HttpResponse:
        tenant_id = services.tenant_for_webhook(token)
        if tenant_id is None:
            return HttpResponse(status=404)
        payment_id = payment_id_from(request)
        if payment_id is None:
            return HttpResponse(status=200)  # merchant_order etc.: nada a fazer

        from .tasks import sync_payment_task

        args = (str(tenant_id), payment_id)
        transaction.on_commit(lambda: sync_payment_task.delay(*args))
        return HttpResponse(status=200)

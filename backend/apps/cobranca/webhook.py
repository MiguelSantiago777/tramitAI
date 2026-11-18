"""Aviso do Mercado Pago sobre as assinaturas do TramitAI (conta da plataforma).

Como no financeiro, o aviso só diz "olhe a assinatura X": a task consulta o MP com o token da
plataforma antes de liberar ou bloquear qualquer coisa.
"""

import json
import re

from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
KINDS = {"subscription_preapproval", "preapproval", "subscription_authorized_payment"}


def event_from(request: HttpRequest) -> tuple[str, str] | None:
    kind = request.GET.get("type") or request.GET.get("topic") or ""
    object_id = request.GET.get("data.id") or request.GET.get("id") or ""
    if request.body:
        try:
            body = json.loads(request.body)
        except ValueError:
            body = {}
        if isinstance(body, dict):
            kind = str(body.get("type") or body.get("topic") or kind)
            data = body.get("data")
            if isinstance(data, dict) and data.get("id"):
                object_id = str(data["id"])
    if kind not in KINDS or not _ID.match(object_id):
        return None
    return kind, object_id


@method_decorator(csrf_exempt, name="dispatch")
class SubscriptionWebhookView(View):
    http_method_names = ["post"]

    def post(self, request: HttpRequest) -> HttpResponse:
        event = event_from(request)
        if event is None:
            return HttpResponse(status=200)
        from .tasks import sync_subscription_event

        transaction.on_commit(lambda: sync_subscription_event.delay(*event))
        return HttpResponse(status=200)

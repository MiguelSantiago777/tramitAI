"""Google Agenda do usuário logado: status, conectar (link do Google) e desconectar.

Falam com o Google por HTTP: fora da transação do request (non_atomic na URL).
"""

import logging
from typing import Any, cast

from django.conf import settings
from django.core import signing
from django.http import HttpRequest, HttpResponseRedirect
from django.views import View
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import get_membership
from apps.accounts.models import User
from apps.agenda import google
from apps.agenda.models import GoogleCalendarConnection
from apps.core import audit
from apps.core.exceptions import ApiError
from apps.core.tenancy import tenant_atomic
from apps.core.views_base import OutsideTransactionMixin

logger = logging.getLogger(__name__)


class GoogleStatusSerializer(serializers.Serializer[Any]):
    configured = serializers.BooleanField()
    connected = serializers.BooleanField()
    google_email = serializers.CharField(allow_blank=True)
    needs_reconnect = serializers.BooleanField()
    busy_synced_at = serializers.DateTimeField(allow_null=True)


class GoogleConnectSerializer(serializers.Serializer[Any]):
    authorization_url = serializers.URLField()


class GoogleCalendarView(OutsideTransactionMixin, APIView):
    def _status(self, request: Request) -> dict[str, Any]:
        membership = get_membership(request)
        with tenant_atomic(membership.tenant_id):
            conn = GoogleCalendarConnection.objects.filter(user=request.user).first()
            return {
                "configured": google.configured(),
                "connected": conn is not None,
                "google_email": conn.google_email if conn else "",
                "needs_reconnect": bool(conn and conn.needs_reconnect),
                "busy_synced_at": conn.busy_synced_at if conn else None,
            }

    @extend_schema(responses=GoogleStatusSerializer, tags=["agenda"])
    def get(self, request: Request) -> Response:
        return Response(GoogleStatusSerializer(self._status(request)).data)

    @extend_schema(request=None, responses=GoogleConnectSerializer, tags=["agenda"])
    def post(self, request: Request) -> Response:
        """Link de autorização do Google (o navegador vai para lá e volta no callback)."""
        if not google.configured():
            raise ApiError(
                "Integração com o Google Agenda ainda não configurada no servidor.",
                code="google_not_configured",
                status_code=503,
            )
        url = google.authorization_url(
            tenant_id=get_membership(request).tenant_id, user=cast(User, request.user)
        )
        return Response(GoogleConnectSerializer({"authorization_url": url}).data)

    @extend_schema(request=None, responses=GoogleStatusSerializer, tags=["agenda"])
    def delete(self, request: Request) -> Response:
        membership = get_membership(request)
        google.disconnect(membership.tenant_id, cast(User, request.user).pk)
        with tenant_atomic(membership.tenant_id):
            audit.record(
                "google_calendar.disconnected",
                membership,
                actor_type=audit.Actor.USER,
                actor_user=cast(User, request.user),
            )
        return Response(GoogleStatusSerializer(self._status(request)).data)


class GoogleCallbackView(View):
    """Volta do Google (sem JWT: quem é e de qual escritório vem no `state` assinado)."""

    http_method_names = ["get"]

    def get(self, request: HttpRequest) -> HttpResponseRedirect:
        back = f"{settings.FRONTEND_URL.rstrip('/')}/agenda?google="
        code, state = request.GET.get("code", ""), request.GET.get("state", "")
        if request.GET.get("error") or not code or not state:
            return HttpResponseRedirect(back + "cancelado")
        try:
            tenant_id, user_id = google.read_state(state)
        except signing.BadSignature:
            return HttpResponseRedirect(back + "expirado")
        try:
            google.connect(tenant_id=tenant_id, user_id=user_id, code=code)
        except google.GoogleError as exc:
            logger.warning("google: conexão falhou (%s)", exc.code)
            return HttpResponseRedirect(back + "erro")
        with tenant_atomic(tenant_id):
            audit.record(
                "google_calendar.connected",
                GoogleCalendarConnection.objects.get(user_id=user_id),
                actor_type=audit.Actor.USER,
                actor_user=User.objects.get(pk=user_id),
            )
        return HttpResponseRedirect(back + "conectado")

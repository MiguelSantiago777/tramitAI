"""Conexão do WhatsApp do escritório (Baileys): status, QR Code para parear e desconectar.

A view roda FORA da transação do request (non_atomic na URL), porque fala com a ponte por
HTTP. Leituras e gravações no banco usam transações curtas com o tenant ativo.
Parear e desconectar: só o titular (quem lê o QR liga o próprio WhatsApp ao sistema).
"""

import contextlib
import uuid
from typing import Any, cast

from django.db import connection, transaction
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import get_membership
from apps.accounts.models import Membership, User
from apps.accounts.permissions import IsOwnerForWrites
from apps.core import audit
from apps.core.tenancy import clear_tenant, tenant_atomic
from apps.whatsapp import services
from apps.whatsapp.gateway import bridge
from apps.whatsapp.models import WhatsAppAccount

_STATUS_FROM_BRIDGE = {
    "open": "connected",
    "qr": "qr",
    "connecting": "connecting",
}


class ConnectionSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=WhatsAppAccount.Provider.choices, allow_null=True)
    # not_configured | qr | connecting | connected | disconnected | bridge_down
    status = serializers.CharField()
    phone = serializers.CharField(allow_blank=True)
    qr = serializers.CharField(allow_null=True)
    can_manage = serializers.BooleanField()


class WhatsAppConnectionView(APIView):
    permission_classes = [IsOwnerForWrites]

    def perform_authentication(self, request: Request) -> None:
        # Autentica numa transação curta (a autenticação ativa o tenant com set_config local).
        with transaction.atomic():
            request.user  # noqa: B018 - dispara a autenticação
        clear_tenant()

    def handle_exception(self, exc: Exception) -> Response:
        # O handler do DRF marca rollback na transação aberta. Esta view não tem transação
        # própria, então não há o que desfazer (e não deve contaminar uma transação externa).
        needs_rollback = connection.needs_rollback
        response = super().handle_exception(exc)
        connection.needs_rollback = needs_rollback
        return response

    def _tenant_id(self, request: Request) -> uuid.UUID:
        return get_membership(request).tenant_id

    def _account(self, tenant_id: uuid.UUID) -> WhatsAppAccount | None:
        with tenant_atomic(tenant_id):
            return (
                WhatsAppAccount.objects.exclude(status=WhatsAppAccount.Status.DISABLED)
                .order_by("created_at")
                .first()
            )

    def _payload(self, request: Request, account: WhatsAppAccount | None) -> dict[str, Any]:
        can_manage = get_membership(request).role == Membership.Role.OWNER
        base: dict[str, Any] = {
            "provider": account.provider if account else None,
            "phone": account.display_phone if account else "",
            "qr": None,
            "can_manage": can_manage,
        }
        if account is None:
            return {**base, "status": "not_configured"}
        if account.provider == WhatsAppAccount.Provider.CLOUD_API:
            return {**base, "status": "connected"}
        try:
            info = bridge.session_info(account.phone_number_id)
        except bridge.BridgeUnavailable:
            return {**base, "status": "bridge_down"}
        status = _STATUS_FROM_BRIDGE.get(info.status, "disconnected")
        return {
            **base,
            "status": status,
            "phone": f"+{info.phone}" if info.phone else base["phone"],
            # O QR liga um WhatsApp ao escritório: só o titular vê.
            "qr": info.qr if status == "qr" and can_manage else None,
        }

    @extend_schema(responses=ConnectionSerializer, tags=["whatsapp"])
    def get(self, request: Request) -> Response:
        account = self._account(self._tenant_id(request))
        return Response(ConnectionSerializer(self._payload(request, account)).data)

    @extend_schema(request=None, responses=ConnectionSerializer, tags=["whatsapp"])
    def post(self, request: Request) -> Response:
        """Conectar: cria a sessão (se preciso) e pede o QR Code à ponte."""
        tenant_id = self._tenant_id(request)
        with tenant_atomic(tenant_id):
            account = services.ensure_baileys_account(
                tenant_id=tenant_id, user=cast(User, request.user)
            )
        # Ponte fora do ar: o payload abaixo já mostra "bridge_down".
        with contextlib.suppress(bridge.BridgeUnavailable):
            bridge.start_session(account.phone_number_id)
        return Response(ConnectionSerializer(self._payload(request, account)).data)

    @extend_schema(request=None, responses=ConnectionSerializer, tags=["whatsapp"])
    def delete(self, request: Request) -> Response:
        """Desconectar: encerra a sessão na ponte (o celular deixa de estar pareado)."""
        tenant_id = self._tenant_id(request)
        account = self._account(tenant_id)
        if account is not None and account.provider == WhatsAppAccount.Provider.BAILEYS:
            with contextlib.suppress(bridge.BridgeUnavailable):
                bridge.logout_session(account.phone_number_id)
            with tenant_atomic(tenant_id):
                WhatsAppAccount.objects.filter(pk=account.pk).update(
                    connection=WhatsAppAccount.Connection.LOGGED_OUT
                )
                audit.record(
                    "whatsapp.disconnected",
                    account,
                    actor_type=audit.Actor.USER,
                    actor_user=request.user,
                )
            account = self._account(tenant_id)
        return Response(ConnectionSerializer(self._payload(request, account)).data)

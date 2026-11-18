import contextlib
from typing import Any

from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.api.serializers import LoginResponseSerializer
from apps.accounts.authentication import TENANT_CLAIM, get_membership
from apps.accounts.permissions import IsOwnerForWrites
from apps.cobranca import services
from apps.cobranca.models import Plan
from apps.core.mercadopago import MercadoPagoError
from apps.core.tenancy import tenant_context
from apps.core.views_base import OutsideTransactionMixin


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ["code", "name", "price", "description", "max_users"]


class BillingSerializer(serializers.Serializer[Any]):
    status = serializers.CharField()
    status_label = serializers.CharField()
    plan_name = serializers.CharField(allow_blank=True)
    price = serializers.CharField(allow_blank=True)
    trial_ends_at = serializers.DateTimeField(allow_null=True)
    paid_until = serializers.DateTimeField(allow_null=True)
    access_until = serializers.DateTimeField(allow_null=True)
    days_left = serializers.IntegerField(allow_null=True)
    blocked = serializers.BooleanField()
    payer_email = serializers.EmailField(allow_blank=True)
    checkout_url = serializers.CharField(allow_blank=True)
    can_manage = serializers.BooleanField()
    exempt = serializers.BooleanField()


class CheckoutSerializer(serializers.Serializer[Any]):
    payer_email = serializers.EmailField()


class CheckoutResponseSerializer(serializers.Serializer[Any]):
    checkout_url = serializers.URLField()


class SignupSerializer(serializers.Serializer[Any]):
    office_name = serializers.CharField(max_length=200)
    full_name = serializers.CharField(max_length=200)
    email = serializers.EmailField()
    password = serializers.CharField(min_length=10, max_length=128, write_only=True)
    accept_terms = serializers.BooleanField()

    def validate_accept_terms(self, value: bool) -> bool:
        if not value:
            raise serializers.ValidationError("É preciso aceitar os termos de uso.")
        return value

    def validate_password(self, value: str) -> str:
        from django.contrib.auth.password_validation import validate_password

        validate_password(value)
        return value


class PlansView(APIView):
    """Planos à venda (página pública de preços)."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(responses=PlanSerializer(many=True), tags=["assinatura"])
    def get(self, request: Request) -> Response:
        plans = Plan.objects.filter(is_active=True)
        return Response(PlanSerializer(plans, many=True).data)


class SignupView(APIView):
    """Cadastro self-service: cria escritório + titular em teste grátis e já entra."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "signup"

    @extend_schema(
        request=SignupSerializer,
        responses={201: LoginResponseSerializer},
        tags=["assinatura"],
    )
    def post(self, request: Request) -> Response:
        from rest_framework_simplejwt.tokens import RefreshToken

        from apps.accounts.api.views import _session_data

        payload = SignupSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        created = services.signup(
            office_name=data["office_name"],
            full_name=data["full_name"],
            email=data["email"],
            password=data["password"],
        )
        refresh = RefreshToken.for_user(created.owner)
        refresh[TENANT_CLAIM] = str(created.tenant.id)
        with tenant_context(created.tenant.id):
            session = _session_data(created.membership)
        body = {"access": str(refresh.access_token), "refresh": str(refresh), "session": session}
        return Response(LoginResponseSerializer(body).data, status=status.HTTP_201_CREATED)


class BillingView(OutsideTransactionMixin, APIView):
    """Assinatura do escritório. Assinar/cancelar: só o titular (fala com o MP: sem transação)."""

    permission_classes = [IsOwnerForWrites]

    def _status(self, request: Request) -> dict[str, Any]:
        membership = get_membership(request)
        with transaction.atomic():
            return services.billing_status(membership.tenant_id, membership).__dict__

    @extend_schema(responses=BillingSerializer, tags=["assinatura"])
    def get(self, request: Request) -> Response:
        return Response(BillingSerializer(self._status(request)).data)

    @extend_schema(
        request=CheckoutSerializer, responses=CheckoutResponseSerializer, tags=["assinatura"]
    )
    def post(self, request: Request) -> Response:
        payload = CheckoutSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        url = services.start_checkout(
            get_membership(request).tenant_id, payer_email=payload.validated_data["payer_email"]
        )
        return Response(CheckoutResponseSerializer({"checkout_url": url}).data)

    @extend_schema(request=None, responses=BillingSerializer, tags=["assinatura"])
    def delete(self, request: Request) -> Response:
        services.cancel(get_membership(request).tenant_id)
        return Response(BillingSerializer(self._status(request)).data)


class BillingRefreshView(OutsideTransactionMixin, APIView):
    """Volta do checkout do MP: confere na hora (sem esperar o aviso)."""

    @extend_schema(request=None, responses=BillingSerializer, tags=["assinatura"])
    def post(self, request: Request) -> Response:
        membership = get_membership(request)
        with transaction.atomic():
            sub = services.subscription_for(membership.tenant_id)
            preapproval_id = sub.mp_preapproval_id if sub else ""
        if preapproval_id:
            # Se o MP não responder agora, o aviso ou o beat confirmam depois.
            with contextlib.suppress(MercadoPagoError):
                services.sync_subscription(preapproval_id)
        with transaction.atomic():
            data = services.billing_status(membership.tenant_id, membership).__dict__
        return Response(BillingSerializer(data).data)

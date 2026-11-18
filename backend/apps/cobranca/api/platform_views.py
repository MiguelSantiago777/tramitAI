"""API do painel da plataforma. Só superusuário (o dono do TramitAI)."""

import uuid
from decimal import Decimal
from typing import Any, cast

from django.db import transaction
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.cobranca import platform, services
from apps.cobranca.models import Plan
from apps.core.exceptions import ApiError
from apps.core.views_base import OutsideTransactionMixin


class IsPlatformAdmin(BasePermission):
    message = "Área exclusiva da administração do TramitAI."

    def has_permission(self, request: Request, view: Any) -> bool:
        user = request.user
        return bool(user and user.is_authenticated and user.is_superuser)


class PlatformAPIView(APIView):
    permission_classes = [IsPlatformAdmin]


class OverviewView(PlatformAPIView):
    @extend_schema(responses=OpenApiTypes.OBJECT, tags=["plataforma"])
    def get(self, request: Request) -> Response:
        return Response(platform.overview())


class OfficesView(PlatformAPIView):
    @extend_schema(
        responses=OpenApiTypes.OBJECT, tags=["plataforma"], operation_id="platform_offices_list"
    )
    def get(self, request: Request) -> Response:
        return Response(
            platform.offices(
                q=request.query_params.get("q", ""),
                status=request.query_params.get("status", ""),
            )
        )


class OfficeDetailView(PlatformAPIView):
    @extend_schema(responses=OpenApiTypes.OBJECT, tags=["plataforma"])
    def get(self, request: Request, office_id: uuid.UUID) -> Response:
        return Response(platform.office(office_id))


class ActionSerializer(serializers.Serializer[Any]):
    days = serializers.IntegerField(required=False, min_value=1, max_value=90)
    exempt = serializers.BooleanField(required=False)
    suspended = serializers.BooleanField(required=False)
    plan_code = serializers.SlugField(required=False)
    amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.01"), required=False
    )
    months = serializers.IntegerField(required=False, min_value=1, max_value=24)
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)


ACTIONS = {"extend-trial", "exempt", "suspend", "plan", "manual-payment"}


class OfficeActionView(PlatformAPIView):
    @extend_schema(request=ActionSerializer, responses=OpenApiTypes.OBJECT, tags=["plataforma"])
    def post(self, request: Request, office_id: uuid.UUID, action: str) -> Response:
        if action not in ACTIONS:
            raise ApiError("Ação desconhecida.", code="not_found", status_code=404)
        payload = ActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        user = cast(User, request.user)

        def need(field: str) -> Any:
            if field not in data:
                raise ApiError(f"Informe {field}.", code="missing_field")
            return data[field]

        if action == "extend-trial":
            platform.extend_trial(office_id, days=need("days"), user=user)
        elif action == "exempt":
            platform.set_exempt(office_id, exempt=need("exempt"), user=user)
        elif action == "suspend":
            platform.set_suspended(office_id, suspended=need("suspended"), user=user)
        elif action == "plan":
            platform.change_plan(office_id, plan_code=need("plan_code"), user=user)
        else:
            platform.manual_payment(
                office_id,
                amount=need("amount"),
                months=data.get("months", 1),
                note=data.get("note", ""),
                user=user,
            )
        return Response(platform.office(office_id))


class PaymentLinkView(OutsideTransactionMixin, APIView):
    """Gera (ou reaproveita) o link de assinatura do Mercado Pago para mandar ao escritório."""

    permission_classes = [IsPlatformAdmin]

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT, tags=["plataforma"])
    def post(self, request: Request, office_id: uuid.UUID) -> Response:
        with transaction.atomic():
            info = platform.office_checkout(office_id)
        if info["checkout_url"]:
            return Response({"checkout_url": info["checkout_url"]})
        if not info["payer_email"]:
            raise ApiError("Escritório sem e-mail do titular.", code="no_email")
        url = services.start_checkout(office_id, payer_email=info["payer_email"])
        return Response({"checkout_url": url})


class PaymentsView(PlatformAPIView):
    @extend_schema(responses=OpenApiTypes.OBJECT, tags=["plataforma"])
    def get(self, request: Request) -> Response:
        return Response(platform.payments())


class PlatformPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ["id", "code", "name", "price", "description", "max_users", "is_active", "sort"]
        read_only_fields = ["id"]


@extend_schema(tags=["plataforma"])
class PlanViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Planos à venda. Sem DELETE: desative (escritórios podem estar nele)."""

    permission_classes = [IsPlatformAdmin]
    serializer_class = PlatformPlanSerializer
    queryset = Plan.objects.all().order_by("sort", "price")
    pagination_class = None
    http_method_names = ["get", "post", "patch"]

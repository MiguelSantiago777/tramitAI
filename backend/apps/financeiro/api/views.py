import uuid
from datetime import date
from typing import Any, cast

from django.db.models import Q, QuerySet
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import get_membership
from apps.accounts.models import Membership, User
from apps.accounts.permissions import IsOwnerForWrites
from apps.core import audit
from apps.core.exceptions import ApiError
from apps.core.tenancy import tenant_atomic
from apps.core.views_base import OutsideTransactionMixin, schema_safe_queryset
from apps.financeiro import services
from apps.financeiro.models import FeeAgreement, Installment

from .serializers import (
    ChargeSerializer,
    FeeAgreementSerializer,
    InstallmentFilterSerializer,
    InstallmentSerializer,
    MercadoPagoConnectSerializer,
    MercadoPagoStatusSerializer,
    SettleSerializer,
    SummarySerializer,
)


@extend_schema(tags=["financeiro"])
class FeeAgreementViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Contratos de honorários. Sem DELETE: cancele (o histórico fica)."""

    serializer_class = FeeAgreementSerializer
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self) -> QuerySet[FeeAgreement]:
        fake = schema_safe_queryset(self, FeeAgreement)
        if fake is not None:
            return fake
        qs = (
            FeeAgreement.objects.select_related("client", "legal_case")
            .prefetch_related("installments__agreement__client", "installments__settled_by")
            .filter(client__deleted_at__isnull=True)  # cliente na lixeira some do financeiro
        )
        client = self.request.query_params.get("client")
        if client:
            qs = qs.filter(client_id=client)
        return qs.order_by("-created_at")

    @extend_schema(parameters=[OpenApiParameter("client", OpenApiTypes.UUID, required=False)])
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer: Any) -> None:
        data = serializer.validated_data
        serializer.instance = services.create_agreement(
            user=cast(User, self.request.user),
            client=data["client"],
            legal_case=data.get("legal_case"),
            title=data.get("title", ""),
            kind=data.get("kind", FeeAgreement.Kind.CONTRATUAL),
            total_amount=data["total_amount"],
            installments=data["installments_count"],
            first_due=data["first_due"],
            entry_amount=data.get("entry_amount"),
            notes=data.get("notes", ""),
        )

    def perform_update(self, serializer: Any) -> None:
        for name in ("installments_count", "first_due", "entry_amount"):
            serializer.validated_data.pop(name, None)
        serializer.save()

    @extend_schema(request=None, responses=FeeAgreementSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, pk: str | None = None) -> Response:
        agreement = self.get_object()
        user = cast(User, request.user)
        for installment in agreement.installments.filter(status=Installment.Status.OPEN):
            services.cancel_installment(installment, user=user)
        agreement.status = FeeAgreement.Status.CANCELLED
        agreement.save(update_fields=["status", "updated_at"])
        audit.record(
            "fees.agreement_cancelled", agreement, actor_type=audit.Actor.USER, actor_user=user
        )
        return Response(FeeAgreementSerializer(self.get_object()).data)


@extend_schema(tags=["financeiro"])
class InstallmentViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = InstallmentSerializer
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self) -> QuerySet[Installment]:
        fake = schema_safe_queryset(self, Installment)
        if fake is not None:
            return fake
        qs = Installment.objects.select_related(
            "agreement__client", "agreement__legal_case", "settled_by"
        ).filter(agreement__client__deleted_at__isnull=True)
        if self.action != "list":
            return qs
        f = InstallmentFilterSerializer(data=self.request.query_params)
        f.is_valid(raise_exception=True)
        data = f.validated_data
        today = timezone.localdate()
        st = data["status"]
        if st == "open":
            qs = qs.filter(status=Installment.Status.OPEN)
        elif st == "overdue":
            qs = qs.filter(status=Installment.Status.OPEN, due_date__lt=today)
        elif st == "paid":
            qs = qs.filter(status=Installment.Status.PAID)
        elif st == "cancelled":
            qs = qs.filter(status=Installment.Status.CANCELLED)
        if data.get("client"):
            qs = qs.filter(agreement__client_id=data["client"])
        if data.get("agreement"):
            qs = qs.filter(agreement_id=data["agreement"])
        if data.get("due_from"):
            qs = qs.filter(due_date__gte=data["due_from"])
        if data.get("due_to"):
            qs = qs.filter(due_date__lte=data["due_to"])
        if data["q"].strip():
            q = data["q"].strip()
            qs = qs.filter(
                Q(agreement__client__name__icontains=q) | Q(agreement__title__icontains=q)
            )
        if st == "paid":
            return qs.order_by("-paid_at")
        return qs.order_by("due_date", "number")

    @extend_schema(parameters=[InstallmentFilterSerializer])
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().list(request, *args, **kwargs)

    def perform_update(self, serializer: Any) -> None:
        installment = cast(Installment, serializer.instance)
        if installment.status != Installment.Status.OPEN:
            raise ApiError("Só parcela em aberto pode ser alterada.", code="installment_not_open")
        if installment.has_active_charge:
            raise ApiError(
                "Esta parcela tem cobrança no Mercado Pago. Gere uma nova cobrança depois de "
                "alterar.",
                code="has_active_charge",
            )
        serializer.save(charge_kind="", charge_expires_at=None, pix_code="", payment_url="")
        audit.record(
            "fees.installment_updated",
            serializer.instance,
            actor_type=audit.Actor.USER,
            actor_user=cast(User, self.request.user),
            data={"fields": sorted(serializer.validated_data.keys())},
        )

    @extend_schema(request=SettleSerializer, responses=InstallmentSerializer)
    @action(detail=True, methods=["post"])
    def settle(self, request: Request, pk: str | None = None) -> Response:
        payload = SettleSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        installment = services.settle(
            self.get_object(),
            user=cast(User, request.user),
            method=data["method"],
            paid_amount=data.get("paid_amount"),
            paid_at=data.get("paid_at"),
            note=data.get("note", ""),
        )
        return Response(InstallmentSerializer(installment).data)

    @extend_schema(request=None, responses=InstallmentSerializer)
    @action(detail=True, methods=["post"])
    def reopen(self, request: Request, pk: str | None = None) -> Response:
        installment = services.reopen(self.get_object(), user=cast(User, request.user))
        return Response(InstallmentSerializer(installment).data)

    @extend_schema(request=None, responses=InstallmentSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, pk: str | None = None) -> Response:
        installment = services.cancel_installment(self.get_object(), user=cast(User, request.user))
        return Response(InstallmentSerializer(installment).data)

    @extend_schema(request=None, responses={202: None})
    @action(detail=True, methods=["post"], url_path="send-whatsapp")
    def send_whatsapp(self, request: Request, pk: str | None = None) -> Response:
        services.send_charge(self.get_object(), user=cast(User, request.user))
        return Response(status=status.HTTP_202_ACCEPTED)

    @extend_schema(
        parameters=[OpenApiParameter("month", OpenApiTypes.STR, description="AAAA-MM")],
        responses=SummarySerializer,
    )
    @action(detail=False, methods=["get"])
    def summary(self, request: Request) -> Response:
        raw = request.query_params.get("month", "")
        try:
            month = date.fromisoformat(f"{raw}-01") if raw else timezone.localdate()
        except ValueError as exc:
            raise ApiError("Mês inválido (use AAAA-MM).", code="invalid_month") from exc
        return Response(SummarySerializer(services.summary(month)).data)


class InstallmentChargeView(OutsideTransactionMixin, APIView):
    """Gera Pix ou link de pagamento no Mercado Pago (HTTP: fora da transação do request)."""

    @extend_schema(request=ChargeSerializer, responses=InstallmentSerializer, tags=["financeiro"])
    def post(self, request: Request, pk: str) -> Response:
        payload = ChargeSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        tenant_id = get_membership(request).tenant_id
        try:
            installment_id = uuid.UUID(pk)
        except ValueError as exc:
            raise ApiError("Parcela não encontrada.", code="not_found", status_code=404) from exc
        services.create_charge(
            tenant_id,
            installment_id,
            kind=payload.validated_data["kind"],
            user=cast(User, request.user),
        )
        with tenant_atomic(tenant_id):
            installment = Installment.objects.select_related(
                "agreement__client", "agreement__legal_case", "settled_by"
            ).get(pk=installment_id)
            return Response(InstallmentSerializer(installment).data)


class MercadoPagoAccountView(OutsideTransactionMixin, APIView):
    """Conta do Mercado Pago do escritório. Conectar/desconectar: só o titular."""

    permission_classes = [IsOwnerForWrites]

    def _payload(self, request: Request) -> dict[str, Any]:
        membership = get_membership(request)
        with tenant_atomic(membership.tenant_id):
            account = services.account()
            webhook = services.webhook_url(membership.tenant_id) if account else ""
            return {
                "connected": account is not None,
                "nickname": account.nickname if account else "",
                "mp_user_id": account.mp_user_id if account else "",
                "can_manage": membership.role == Membership.Role.OWNER,
                "webhook_ready": bool(webhook),
            }

    @extend_schema(responses=MercadoPagoStatusSerializer, tags=["financeiro"])
    def get(self, request: Request) -> Response:
        return Response(MercadoPagoStatusSerializer(self._payload(request)).data)

    @extend_schema(
        request=MercadoPagoConnectSerializer,
        responses=MercadoPagoStatusSerializer,
        tags=["financeiro"],
    )
    def put(self, request: Request) -> Response:
        payload = MercadoPagoConnectSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        services.connect_account(
            get_membership(request).tenant_id,
            token=payload.validated_data["access_token"],
            user=cast(User, request.user),
        )
        return Response(MercadoPagoStatusSerializer(self._payload(request)).data)

    @extend_schema(request=None, responses=MercadoPagoStatusSerializer, tags=["financeiro"])
    def delete(self, request: Request) -> Response:
        with tenant_atomic(get_membership(request).tenant_id):
            services.disconnect_account(user=cast(User, request.user))
        return Response(MercadoPagoStatusSerializer(self._payload(request)).data)

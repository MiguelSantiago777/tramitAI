from decimal import Decimal
from typing import Any

from django.db.models import Sum
from rest_framework import serializers

from apps.clientes.models import Client
from apps.core.serializers import TenantScopedPrimaryKeyRelatedField
from apps.financeiro.models import FeeAgreement, Installment
from apps.processos.models import LegalCase


def money_field(**kwargs: Any) -> serializers.DecimalField:
    return serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01"), **kwargs
    )


class InstallmentSerializer(serializers.ModelSerializer):
    agreement_id = serializers.UUIDField(read_only=True)
    agreement_title = serializers.CharField(source="agreement.title", read_only=True)
    client_id = serializers.UUIDField(source="agreement.client_id", read_only=True)
    client_name = serializers.CharField(source="agreement.client.name", read_only=True)
    case_number = serializers.SerializerMethodField()
    is_overdue = serializers.BooleanField(read_only=True)
    has_active_charge = serializers.BooleanField(read_only=True)
    settled_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Installment
        fields = [
            "id",
            "agreement_id",
            "agreement_title",
            "client_id",
            "client_name",
            "case_number",
            "number",
            "due_date",
            "amount",
            "status",
            "is_overdue",
            "paid_at",
            "paid_amount",
            "method",
            "paid_note",
            "settled_by_name",
            "charge_kind",
            "has_active_charge",
            "pix_code",
            "pix_qr_base64",
            "payment_url",
            "charge_expires_at",
            "last_reminder_on",
        ]
        read_only_fields = [f for f in fields if f not in ("due_date", "amount")]

    def get_case_number(self, obj: Installment) -> str:
        case = obj.agreement.legal_case
        return case.cnj_formatted if case else ""

    def get_settled_by_name(self, obj: Installment) -> str:
        user = obj.settled_by
        return (user.full_name or user.email) if user else ""

    def validate_amount(self, value: Decimal) -> Decimal:
        if value <= 0:
            raise serializers.ValidationError("O valor precisa ser maior que zero.")
        return value


class FeeAgreementSerializer(serializers.ModelSerializer):
    client_id = TenantScopedPrimaryKeyRelatedField(model=Client, source="client")
    client_name = serializers.CharField(source="client.name", read_only=True)
    legal_case_id = TenantScopedPrimaryKeyRelatedField(
        model=LegalCase, source="legal_case", required=False, allow_null=True
    )
    case_number = serializers.SerializerMethodField()
    installments = InstallmentSerializer(many=True, read_only=True)
    paid_total = serializers.SerializerMethodField()
    open_total = serializers.SerializerMethodField()
    # Só na criação: como dividir.
    installments_count = serializers.IntegerField(
        write_only=True, min_value=1, max_value=120, required=False
    )
    first_due = serializers.DateField(write_only=True, required=False)
    entry_amount = money_field(write_only=True, required=False, allow_null=True)

    class Meta:
        model = FeeAgreement
        fields = [
            "id",
            "client_id",
            "client_name",
            "legal_case_id",
            "case_number",
            "title",
            "kind",
            "total_amount",
            "status",
            "notes",
            "installments",
            "paid_total",
            "open_total",
            "installments_count",
            "first_due",
            "entry_amount",
            "created_at",
        ]
        read_only_fields = ["id", "status", "created_at"]
        extra_kwargs = {
            "title": {"required": False, "allow_blank": True},
            "total_amount": {"min_value": Decimal("0.01")},
        }

    def get_case_number(self, obj: FeeAgreement) -> str:
        return obj.legal_case.cnj_formatted if obj.legal_case else ""

    def _sum(self, obj: FeeAgreement, status: str, field: str) -> str:
        value = obj.installments.filter(status=status).aggregate(v=Sum(field))["v"]
        return f"{value or Decimal('0'):.2f}"  # mesmo formato dos outros valores (texto)

    def get_paid_total(self, obj: FeeAgreement) -> str:
        return self._sum(obj, Installment.Status.PAID, "paid_amount")

    def get_open_total(self, obj: FeeAgreement) -> str:
        return self._sum(obj, Installment.Status.OPEN, "amount")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if self.instance is None:
            missing = [f for f in ("installments_count", "first_due") if attrs.get(f) is None]
            if missing:
                raise serializers.ValidationError(
                    {f: "Obrigatório para criar o contrato." for f in missing}
                )
        elif "total_amount" in attrs or "client" in attrs:
            raise serializers.ValidationError(
                "Valor e cliente não mudam depois de criado: ajuste as parcelas."
            )
        return attrs


class SettleSerializer(serializers.Serializer[Any]):
    method = serializers.ChoiceField(choices=Installment.Method.choices)
    paid_amount = money_field(required=False, allow_null=True)
    paid_at = serializers.DateTimeField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)


class ChargeSerializer(serializers.Serializer[Any]):
    kind = serializers.ChoiceField(
        choices=[Installment.ChargeKind.PIX, Installment.ChargeKind.LINK]
    )


class InstallmentFilterSerializer(serializers.Serializer[Any]):
    # open = em aberto (inclui vencidas) | overdue | paid | cancelled
    status = serializers.ChoiceField(
        choices=["", "open", "overdue", "paid", "cancelled"], required=False, default=""
    )
    client = serializers.UUIDField(required=False)
    agreement = serializers.UUIDField(required=False)
    due_from = serializers.DateField(required=False)
    due_to = serializers.DateField(required=False)
    q = serializers.CharField(required=False, allow_blank=True, default="", max_length=100)


class SummarySerializer(serializers.Serializer[Any]):
    month = serializers.DateField()
    received = serializers.DecimalField(max_digits=14, decimal_places=2)
    expected = serializers.DecimalField(max_digits=14, decimal_places=2)
    overdue_total = serializers.DecimalField(max_digits=14, decimal_places=2)
    overdue_count = serializers.IntegerField()
    next_30_days = serializers.DecimalField(max_digits=14, decimal_places=2)
    open_total = serializers.DecimalField(max_digits=14, decimal_places=2)


class MercadoPagoStatusSerializer(serializers.Serializer[Any]):
    connected = serializers.BooleanField()
    nickname = serializers.CharField(allow_blank=True)
    mp_user_id = serializers.CharField(allow_blank=True)
    can_manage = serializers.BooleanField()
    webhook_ready = serializers.BooleanField()


class MercadoPagoConnectSerializer(serializers.Serializer[Any]):
    access_token = serializers.CharField(max_length=200, trim_whitespace=True)

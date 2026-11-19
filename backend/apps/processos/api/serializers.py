from typing import Any

from rest_framework import serializers

from apps.accounts.models import User
from apps.clientes.models import Client
from apps.core.serializers import TenantScopedPrimaryKeyRelatedField
from apps.core.tenancy import get_current_tenant_id
from apps.processos.cnj import is_valid_cnj, normalize_cnj
from apps.processos.models import CaseClient, CaseMovement, LegalCase
from apps.processos.selectors import cnj_in_use


class TenantMemberField(serializers.PrimaryKeyRelatedField):
    """Usuário com vínculo ativo no escritório corrente."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("pk_field", serializers.UUIDField())
        super().__init__(**kwargs)

    def get_queryset(self) -> Any:
        return User.objects.filter(
            is_active=True,
            memberships__tenant_id=get_current_tenant_id(),
            memberships__is_active=True,
        )


class CaseClientSerializer(serializers.Serializer):
    client_id = TenantScopedPrimaryKeyRelatedField(model=Client, source="client")
    client_name = serializers.CharField(source="client.name", read_only=True)
    role = serializers.ChoiceField(choices=CaseClient.Role.choices, default=CaseClient.Role.AUTHOR)


class LegalCaseSerializer(serializers.ModelSerializer):
    cnj_number = serializers.CharField(max_length=30)
    cnj_formatted = serializers.CharField(read_only=True)
    tribunal = serializers.CharField(source="tribunal_label", read_only=True)
    responsible_id = TenantMemberField(source="responsible", required=False, allow_null=True)
    responsible_name = serializers.SerializerMethodField()
    clients = CaseClientSerializer(many=True, source="case_clients", required=False)
    pending_movements = serializers.SerializerMethodField()

    def to_representation(self, instance: LegalCase) -> dict[str, Any]:
        data = super().to_representation(instance)
        # Cliente na lixeira não aparece no processo.
        trashed = {str(cc.client_id) for cc in instance.case_clients.all() if cc.client.deleted_at}
        data["clients"] = [c for c in data["clients"] if str(c["client_id"]) not in trashed]
        return data

    class Meta:
        model = LegalCase
        fields = [
            "id",
            "cnj_number",
            "cnj_formatted",
            "tribunal",
            "classe",
            "assunto",
            "orgao_julgador",
            "responsible_id",
            "responsible_name",
            "status",
            "monitoring_enabled",
            "last_checked_at",
            "last_movement_at",
            "sync_status",
            "sync_error",
            "pending_movements",
            "notes",
            "clients",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "last_checked_at",
            "last_movement_at",
            "sync_status",
            "sync_error",
            "created_at",
            "updated_at",
        ]

    def get_pending_movements(self, obj: LegalCase) -> int:
        """Andamentos novos ainda sem aviso ao cliente (anotado na listagem)."""
        annotated = getattr(obj, "pending_movement_count", None)
        if annotated is not None:
            return int(annotated)
        return obj.movements.filter(notification=CaseMovement.Notification.PENDING).count()

    def get_responsible_name(self, obj: LegalCase) -> str:
        user = obj.responsible
        return (user.full_name or user.email) if user else ""

    def validate_cnj_number(self, value: str) -> str:
        digits = normalize_cnj(value)
        if not is_valid_cnj(digits):
            raise serializers.ValidationError(
                "Número CNJ inválido. Confira os 20 dígitos (NNNNNNN-DD.AAAA.J.TR.OOOO)."
            )
        instance: LegalCase | None = self.instance
        if cnj_in_use(digits, exclude_id=instance.pk if instance else None):
            trashed = LegalCase.with_deleted.filter(
                cnj_number=digits, deleted_at__isnull=False
            ).exists()
            raise serializers.ValidationError(
                "Este processo está na Lixeira. Restaure-o por lá."
                if trashed
                else "Este processo já está cadastrado."
            )
        return digits

    def validate_clients(self, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ids = [item["client"].pk for item in value]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("O mesmo cliente aparece mais de uma vez.")
        return value


class CaseFilterSerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True, default="")
    status = serializers.ChoiceField(
        choices=LegalCase.Status.choices, required=False, allow_blank=True, default=""
    )
    client_id = serializers.UUIDField(required=False, allow_null=True, default=None)


class CaseMovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = CaseMovement
        fields = ["id", "name", "code", "complements", "grau", "occurred_at", "notification"]
        read_only_fields = fields

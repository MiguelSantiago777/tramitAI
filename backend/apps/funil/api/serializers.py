from typing import Any

from rest_framework import serializers

from apps.clientes.models import Client
from apps.core.br import normalize_br_phone
from apps.core.serializers import TenantScopedPrimaryKeyRelatedField
from apps.funil.models import Opportunity
from apps.processos.api.serializers import TenantMemberField


class OpportunitySerializer(serializers.ModelSerializer):
    client_id = TenantScopedPrimaryKeyRelatedField(
        model=Client, source="client", required=False, allow_null=True
    )
    client_name = serializers.CharField(source="client.name", read_only=True)
    client_phone = serializers.CharField(source="client.phone_e164", read_only=True)
    client_status = serializers.CharField(source="client.status", read_only=True)
    owner_id = TenantMemberField(source="owner", required=False, allow_null=True)
    owner_name = serializers.SerializerMethodField()
    conversation_id = serializers.UUIDField(read_only=True, allow_null=True)
    # Lead novo direto do quadro (sem cliente cadastrado): nome e telefone.
    new_client_name = serializers.CharField(write_only=True, required=False, max_length=200)
    new_client_phone = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=30
    )

    class Meta:
        model = Opportunity
        fields = [
            "id",
            "title",
            "client_id",
            "client_name",
            "client_phone",
            "client_status",
            "new_client_name",
            "new_client_phone",
            "stage",
            "area",
            "source",
            "estimated_value",
            "owner_id",
            "owner_name",
            "conversation_id",
            "notes",
            "lost_reason",
            "position",
            "stage_changed_at",
            "closed_at",
            "created_at",
            "updated_at",
        ]
        # Sem assunto, vira "Caso de <cliente>".
        extra_kwargs = {"title": {"required": False, "allow_blank": True}}
        # Etapa e ordem mudam pela ação "mover" (registra histórico e regras).
        read_only_fields = [
            "id",
            "stage",
            "lost_reason",
            "position",
            "stage_changed_at",
            "closed_at",
            "created_at",
            "updated_at",
        ]

    def get_owner_name(self, obj: Opportunity) -> str:
        user = obj.owner
        return (user.full_name or user.email) if user else ""

    def validate_new_client_phone(self, value: str) -> str:
        if not value:
            return ""
        normalized = normalize_br_phone(value)
        if not normalized:
            raise serializers.ValidationError("Telefone inválido. Use DDD + número.")
        return normalized

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if self.instance is None and not attrs.get("client") and not attrs.get("new_client_name"):
            raise serializers.ValidationError(
                {"client_id": "Escolha um cliente ou informe o nome do novo contato."}
            )
        return attrs


class MoveSerializer(serializers.Serializer):
    stage = serializers.ChoiceField(choices=Opportunity.Stage.choices)
    position = serializers.IntegerField(required=False, min_value=0, allow_null=True)
    lost_reason = serializers.CharField(required=False, allow_blank=True, max_length=255)


class OpportunityFilterSerializer(serializers.Serializer):
    stage = serializers.ChoiceField(
        choices=Opportunity.Stage.choices, required=False, allow_blank=True, default=""
    )
    owner = serializers.CharField(required=False, allow_blank=True, default="")
    q = serializers.CharField(required=False, allow_blank=True, default="")
    # Quadro: abertas + fechadas nos últimos N dias.
    closed_days = serializers.IntegerField(required=False, min_value=0, max_value=365, default=30)
    client_id = serializers.UUIDField(required=False, allow_null=True, default=None)


class BoardSummarySerializer(serializers.Serializer):
    open_count = serializers.IntegerField()
    by_stage = serializers.DictField(child=serializers.IntegerField())
    open_value = serializers.DecimalField(max_digits=14, decimal_places=2)
    won_count = serializers.IntegerField()
    lost_count = serializers.IntegerField()
    won_value = serializers.DecimalField(max_digits=14, decimal_places=2)
    conversion_rate = serializers.FloatField(allow_null=True)
    period_days = serializers.IntegerField()

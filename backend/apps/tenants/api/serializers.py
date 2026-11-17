from rest_framework import serializers

from apps.accounts.models import Membership
from apps.tenants.models import ClientTermVersion, Tenant, TenantSettings


class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ["id", "name", "slug", "status"]
        read_only_fields = fields


class TenantSettingsSerializer(serializers.ModelSerializer):
    """Configurações do escritório. Edição: só o titular (permissão na view)."""

    tenant_name = serializers.CharField(max_length=200, required=False, trim_whitespace=True)

    class Meta:
        model = TenantSettings
        fields = [
            "id",
            "tenant_name",
            "auto_send_simple_replies",
            "staff_can_approve",
            "ai_triage_enabled",
            "data_retention_days",
            "message_retention_days",
            "timezone",
            "updated_at",
        ]
        # A IA nunca envia sozinha: auto_send fica só leitura (sempre desligado por ora).
        read_only_fields = [
            "id",
            "auto_send_simple_replies",
            "data_retention_days",
            "message_retention_days",
            "timezone",
            "updated_at",
        ]

    def to_representation(self, instance: TenantSettings) -> dict[str, object]:
        data = super().to_representation(instance)
        data["tenant_name"] = Tenant.objects.get(pk=instance.tenant_id).name
        return data

    def validate_tenant_name(self, value: str) -> str:
        if not value:
            raise serializers.ValidationError("Informe o nome do escritório.")
        return value


class ClientTermVersionSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ClientTermVersion
        fields = ["id", "version", "body", "is_active", "created_at", "created_by_name"]
        read_only_fields = ["id", "version", "is_active", "created_at", "created_by_name"]
        extra_kwargs = {"body": {"trim_whitespace": True}}

    def get_created_by_name(self, obj: ClientTermVersion) -> str:
        user = obj.created_by
        return (user.full_name or user.email) if user else ""


class MemberSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(source="user.id", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)

    class Meta:
        model = Membership
        fields = ["user_id", "email", "full_name", "role"]
        read_only_fields = fields


class TeamMemberSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="membership.id")
    user_id = serializers.UUIDField(source="membership.user.id")
    email = serializers.EmailField(source="membership.user.email")
    full_name = serializers.CharField(source="membership.user.full_name")
    role = serializers.ChoiceField(choices=Membership.Role.choices, source="membership.role")
    is_active = serializers.BooleanField(source="membership.is_active")
    pending = serializers.BooleanField()
    is_me = serializers.SerializerMethodField()

    def get_is_me(self, obj: object) -> bool:
        request = self.context.get("request")
        membership = getattr(obj, "membership", None)
        return bool(request and membership and membership.user_id == request.user.pk)


class InviteSerializer(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    role = serializers.ChoiceField(choices=Membership.Role.choices)


class MemberUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=Membership.Role.choices, required=False)
    is_active = serializers.BooleanField(required=False)

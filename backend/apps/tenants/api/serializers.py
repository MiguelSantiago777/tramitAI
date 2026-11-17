from rest_framework import serializers

from apps.accounts.models import Membership
from apps.tenants.models import ClientTermVersion, Tenant, TenantSettings


class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ["id", "name", "slug", "status"]
        read_only_fields = fields


class TenantSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantSettings
        fields = [
            "id",
            "auto_send_simple_replies",
            "staff_can_approve",
            "ai_triage_enabled",
            "data_retention_days",
            "message_retention_days",
            "timezone",
            "updated_at",
        ]
        # Edição chega numa etapa futura (tela de configurações + auditoria).
        read_only_fields = fields


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

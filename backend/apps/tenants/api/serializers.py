from rest_framework import serializers

from apps.tenants.models import Tenant, TenantSettings


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
            "data_retention_days",
            "message_retention_days",
            "timezone",
            "updated_at",
        ]
        # Edição chega numa etapa futura (tela de configurações + auditoria).
        read_only_fields = fields

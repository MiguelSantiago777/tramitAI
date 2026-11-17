from rest_framework import serializers

from apps.accounts.models import Membership, User
from apps.tenants.api.serializers import TenantSerializer


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    tenant_id = serializers.UUIDField(required=False, allow_null=True)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "full_name", "oab_number"]
        read_only_fields = fields


class SessionSerializer(serializers.Serializer):
    """Quem está logado e em qual escritório."""

    user = UserSerializer()
    tenant = TenantSerializer()
    role = serializers.ChoiceField(choices=Membership.Role.choices)
    can_approve = serializers.BooleanField()


class LoginResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    session = SessionSerializer()

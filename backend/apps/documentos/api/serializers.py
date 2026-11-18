from typing import Any

from rest_framework import serializers

from apps.clientes.models import Client
from apps.core.serializers import TenantScopedPrimaryKeyRelatedField
from apps.documentos.models import Document
from apps.documentos.services import INLINE_TYPES
from apps.processos.models import LegalCase


class DocumentSerializer(serializers.ModelSerializer):
    client_id = TenantScopedPrimaryKeyRelatedField(
        model=Client, source="client", required=False, allow_null=True
    )
    client_name = serializers.SerializerMethodField()
    legal_case_id = TenantScopedPrimaryKeyRelatedField(
        model=LegalCase, source="legal_case", required=False, allow_null=True
    )
    case_number = serializers.SerializerMethodField()
    conversation_id = serializers.UUIDField(read_only=True, allow_null=True)
    message_id = serializers.UUIDField(read_only=True, allow_null=True)
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    uploaded_by_name = serializers.SerializerMethodField()
    can_preview = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id",
            "name",
            "content_type",
            "size",
            "category",
            "category_label",
            "description",
            "source",
            "client_id",
            "client_name",
            "legal_case_id",
            "case_number",
            "conversation_id",
            "message_id",
            "uploaded_by_name",
            "can_preview",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "content_type",
            "size",
            "source",
            "conversation_id",
            "message_id",
            "created_at",
        ]

    def get_client_name(self, obj: Document) -> str:
        client = obj.client or (obj.conversation.client if obj.conversation else None)
        return client.name if client else ""

    def get_case_number(self, obj: Document) -> str:
        return obj.legal_case.cnj_formatted if obj.legal_case else ""

    def get_uploaded_by_name(self, obj: Document) -> str:
        user = obj.uploaded_by
        return (user.full_name or user.email) if user else ""

    def get_can_preview(self, obj: Document) -> bool:
        return obj.content_type in INLINE_TYPES

    def validate_name(self, value: str) -> str:
        from apps.documentos.services import safe_filename

        return safe_filename(value)


class DocumentUploadSerializer(serializers.Serializer[Any]):
    file = serializers.FileField(allow_empty_file=True)  # vazio: erro claro no service
    client_id = TenantScopedPrimaryKeyRelatedField(
        model=Client, source="client", required=False, allow_null=True
    )
    legal_case_id = TenantScopedPrimaryKeyRelatedField(
        model=LegalCase, source="legal_case", required=False, allow_null=True
    )
    category = serializers.ChoiceField(
        choices=Document.Category.choices, default=Document.Category.OUTRO
    )
    description = serializers.CharField(required=False, allow_blank=True, max_length=500)


class DocumentFilterSerializer(serializers.Serializer[Any]):
    client = serializers.UUIDField(required=False)
    legal_case = serializers.UUIDField(required=False)
    conversation = serializers.UUIDField(required=False)
    category = serializers.ChoiceField(choices=Document.Category.choices, required=False)
    q = serializers.CharField(required=False, allow_blank=True, default="", max_length=100)

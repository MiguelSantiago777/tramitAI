from datetime import datetime
from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.clientes.models import Client
from apps.core.serializers import TenantScopedPrimaryKeyRelatedField
from apps.processos.api.serializers import TenantMemberField
from apps.whatsapp import services
from apps.whatsapp.models import Conversation, Message, QuickReply

PREVIEW_LENGTH = 140


class LastMessageSerializer(serializers.Serializer):
    direction = serializers.CharField()
    type = serializers.CharField()
    status = serializers.CharField()
    preview = serializers.CharField()


class ConversationSerializer(serializers.ModelSerializer):
    phone = serializers.SerializerMethodField()
    client_id = TenantScopedPrimaryKeyRelatedField(
        model=Client, source="client", required=False, allow_null=True
    )
    client_name = serializers.CharField(source="client.name", read_only=True, default="")
    suggested_client_id = serializers.UUIDField(read_only=True, allow_null=True)
    suggested_client_name = serializers.CharField(
        source="suggested_client.name", read_only=True, default=""
    )
    pending_drafts = serializers.IntegerField(read_only=True, default=0)
    assignee_id = TenantMemberField(source="assignee", required=False, allow_null=True)
    assignee_name = serializers.SerializerMethodField()
    window_open = serializers.SerializerMethodField()
    window_expires_at = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            "id",
            "wa_id",
            "phone",
            "contact_name",
            "client_id",
            "client_name",
            "suggested_client_id",
            "suggested_client_name",
            "pending_drafts",
            "assignee_id",
            "assignee_name",
            "ai_consent_version",
            "status",
            "last_inbound_at",
            "last_message_at",
            "unread_count",
            "window_open",
            "window_expires_at",
            "last_message",
        ]
        read_only_fields = [
            "id",
            "wa_id",
            "contact_name",
            "last_inbound_at",
            "last_message_at",
            "unread_count",
            "ai_consent_version",
        ]

    def get_assignee_name(self, obj: Conversation) -> str:
        user = obj.assignee
        return (user.full_name or user.email) if user else ""

    def get_phone(self, obj: Conversation) -> str:
        return f"+{obj.wa_id}"

    def get_window_open(self, obj: Conversation) -> bool:
        return services.window_open(obj)

    def get_window_expires_at(self, obj: Conversation) -> datetime | None:
        return services.window_expires_at(obj)

    @staticmethod
    def _preview(direction: str, kind: str, status: str, body: str) -> dict[str, Any]:
        text = body if body else f"[{Message.Type(kind).label}]" if kind else ""
        if len(text) > PREVIEW_LENGTH:
            text = text[: PREVIEW_LENGTH - 1] + "…"
        return {"direction": direction, "type": kind, "status": status, "preview": text}

    def get_last_message(self, obj: Conversation) -> dict[str, Any] | None:
        direction = getattr(obj, "last_direction", None)
        if direction is None:
            return None
        return self._preview(
            direction,
            getattr(obj, "last_type", "") or "",
            getattr(obj, "last_status", "") or "",
            getattr(obj, "last_body", "") or "",
        )


class MessageDocumentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    content_type = serializers.CharField()
    size = serializers.IntegerField()


class MessageSerializer(serializers.ModelSerializer):
    sent_by_name = serializers.SerializerMethodField()
    document = serializers.SerializerMethodField()
    # Mídia recebida que ainda está sendo guardada (a tela mostra "baixando...").
    media_pending = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            "id",
            "direction",
            "type",
            "body",
            "status",
            "error_detail",
            "sent_by_name",
            "document",
            "media_pending",
            "wa_timestamp",
            "delivered_at",
            "read_at",
            "created_at",
        ]
        read_only_fields = fields

    @extend_schema_field(MessageDocumentSerializer(allow_null=True))
    def get_document(self, obj: Message) -> dict[str, Any] | None:
        doc = getattr(obj, "document", None)
        if doc is None:
            return None
        return {"id": doc.pk, "name": doc.name, "content_type": doc.content_type, "size": doc.size}

    def get_media_pending(self, obj: Message) -> bool:
        return bool(obj.media_id) and not obj.error_code and getattr(obj, "document", None) is None

    def get_sent_by_name(self, obj: Message) -> str:
        user = obj.sent_by
        return (user.full_name or user.email) if user else ""


class SendMessageSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=services.MAX_TEXT_LENGTH, trim_whitespace=True)


class ConversationFilterSerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True, default="")
    status = serializers.ChoiceField(
        choices=Conversation.Status.choices, required=False, allow_blank=True, default=""
    )
    unread = serializers.BooleanField(required=False, default=False)
    # "me" = minhas; "none" = sem responsável.
    assignee = serializers.ChoiceField(
        choices=["", "me", "none"], required=False, allow_blank=True, default=""
    )


class QuickReplySerializer(serializers.ModelSerializer):
    class Meta:
        model = QuickReply
        fields = ["id", "title", "body", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {"body": {"trim_whitespace": True}, "title": {"trim_whitespace": True}}

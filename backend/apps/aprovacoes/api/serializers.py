from typing import Any

from rest_framework import serializers

from apps.aprovacoes.models import OutboundDraft
from apps.core.models import AuditEvent
from apps.whatsapp.services import MAX_TEXT_LENGTH, window_open


def _user_name(user: Any) -> str:
    return (user.full_name or user.email) if user else ""


class AuditEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = AuditEvent
        fields = ["action", "actor_type", "actor_name", "data", "created_at"]
        read_only_fields = fields

    def get_actor_name(self, obj: AuditEvent) -> str:
        return _user_name(obj.actor_user)


class DraftSerializer(serializers.ModelSerializer):
    conversation_id = serializers.UUIDField(read_only=True)
    contact_name = serializers.CharField(source="conversation.contact_name", read_only=True)
    phone = serializers.SerializerMethodField()
    client_id = serializers.UUIDField(read_only=True, allow_null=True)
    client_name = serializers.CharField(source="client.name", read_only=True, default="")
    source_text = serializers.CharField(source="source_message.body", read_only=True, default="")
    decided_by_name = serializers.SerializerMethodField()
    window_open = serializers.SerializerMethodField()
    sent_message_status = serializers.CharField(
        source="sent_message.status", read_only=True, default=""
    )
    original_ai_text = serializers.SerializerMethodField()

    class Meta:
        model = OutboundDraft
        fields = [
            "id",
            "conversation_id",
            "contact_name",
            "phone",
            "client_id",
            "client_name",
            "origin",
            "status",
            "generated_body",
            "final_body",
            "original_ai_text",
            "intent",
            "urgency",
            "needs_lawyer",
            "summary",
            "guardrail_flags",
            "source_text",
            "window_open",
            "decided_by_name",
            "decided_at",
            "rejection_reason",
            "failure_detail",
            "sent_message_status",
            "created_at",
        ]
        read_only_fields = fields

    def get_phone(self, obj: OutboundDraft) -> str:
        return f"+{obj.conversation.wa_id}"

    def get_decided_by_name(self, obj: OutboundDraft) -> str:
        return _user_name(obj.decided_by)

    def get_window_open(self, obj: OutboundDraft) -> bool:
        return window_open(obj.conversation)

    def get_original_ai_text(self, obj: OutboundDraft) -> str:
        """Texto que a IA escreveu e os guardrails bloquearam (só para o advogado ver)."""
        if not obj.guardrail_flags or obj.generation is None:
            return ""
        data = obj.generation.output_data or {}
        return str(data.get("reply", ""))


class DraftDetailSerializer(DraftSerializer):
    history = serializers.SerializerMethodField()

    class Meta(DraftSerializer.Meta):
        fields = [*DraftSerializer.Meta.fields, "history"]
        read_only_fields = fields

    def get_history(self, obj: OutboundDraft) -> list[dict[str, Any]]:
        from apps.core.audit import history

        return list(AuditEventSerializer(history(obj), many=True).data)


class ApproveSerializer(serializers.Serializer):
    body = serializers.CharField(
        required=False, max_length=MAX_TEXT_LENGTH, trim_whitespace=True, allow_blank=False
    )


class RejectSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255, default="")


class DraftFilterSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=OutboundDraft.Status.choices, required=False, allow_blank=True, default=""
    )
    conversation_id = serializers.UUIDField(required=False, allow_null=True, default=None)

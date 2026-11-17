from typing import Any

from rest_framework import serializers

from apps.agenda.models import Event, Task
from apps.clientes.models import Client
from apps.core.serializers import TenantScopedPrimaryKeyRelatedField
from apps.processos.api.serializers import TenantMemberField
from apps.processos.models import LegalCase


def _name(user: Any) -> str:
    return (user.full_name or user.email) if user else ""


class TaskSerializer(serializers.ModelSerializer):
    assignee_id = TenantMemberField(source="assignee", required=False, allow_null=True)
    assignee_name = serializers.SerializerMethodField()
    client_id = TenantScopedPrimaryKeyRelatedField(
        model=Client, source="client", required=False, allow_null=True
    )
    client_name = serializers.CharField(source="client.name", read_only=True, default="")
    legal_case_id = TenantScopedPrimaryKeyRelatedField(
        model=LegalCase, source="legal_case", required=False, allow_null=True
    )
    case_number = serializers.CharField(
        source="legal_case.cnj_formatted", read_only=True, default=""
    )
    completed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = [
            "id",
            "title",
            "description",
            "kind",
            "status",
            "priority",
            "due_date",
            "due_time",
            "assignee_id",
            "assignee_name",
            "client_id",
            "client_name",
            "legal_case_id",
            "case_number",
            "source",
            "completed_at",
            "completed_by_name",
            "created_at",
            "updated_at",
        ]
        # Status muda pelas ações concluir/reabrir (ou cancelar via PATCH).
        read_only_fields = ["id", "source", "completed_at", "created_at", "updated_at"]

    def get_assignee_name(self, obj: Task) -> str:
        return _name(obj.assignee)

    def get_completed_by_name(self, obj: Task) -> str:
        return _name(obj.completed_by)

    def validate_status(self, value: str) -> str:
        # Concluir tem ação própria (registra quem e quando).
        if value == Task.Status.DONE:
            raise serializers.ValidationError("Use a ação de concluir.")
        return value


class EventSerializer(serializers.ModelSerializer):
    responsible_id = TenantMemberField(source="responsible", required=False, allow_null=True)
    responsible_name = serializers.SerializerMethodField()
    client_id = TenantScopedPrimaryKeyRelatedField(
        model=Client, source="client", required=False, allow_null=True
    )
    client_name = serializers.CharField(source="client.name", read_only=True, default="")
    legal_case_id = TenantScopedPrimaryKeyRelatedField(
        model=LegalCase, source="legal_case", required=False, allow_null=True
    )
    case_number = serializers.CharField(
        source="legal_case.cnj_formatted", read_only=True, default=""
    )

    class Meta:
        model = Event
        fields = [
            "id",
            "title",
            "kind",
            "status",
            "starts_at",
            "ends_at",
            "location",
            "notes",
            "responsible_id",
            "responsible_name",
            "client_id",
            "client_name",
            "legal_case_id",
            "case_number",
            "remind_client",
            "client_reminded_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "client_reminded_at", "created_at", "updated_at"]

    def get_responsible_name(self, obj: Event) -> str:
        return _name(obj.responsible)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        instance: Event | None = self.instance
        starts = attrs.get("starts_at", instance.starts_at if instance else None)
        ends = attrs.get("ends_at", instance.ends_at if instance else None)
        if starts and ends and ends < starts:
            raise serializers.ValidationError({"ends_at": "O fim precisa ser depois do início."})
        client = attrs.get("client", instance.client if instance else None)
        if attrs.get("remind_client") and client is None:
            raise serializers.ValidationError(
                {"remind_client": "Escolha o cliente para enviar o lembrete."}
            )
        return attrs


class TaskFilterSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=Task.Status.choices, required=False, allow_blank=True, default=""
    )
    # "me" = minhas; "none" = sem responsável; ou o id de um membro.
    assignee = serializers.CharField(required=False, allow_blank=True, default="")
    due = serializers.ChoiceField(
        choices=["", "overdue", "today", "week", "none"], required=False, default=""
    )
    client_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    case_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    q = serializers.CharField(required=False, allow_blank=True, default="")


class EventFilterSerializer(serializers.Serializer):
    start = serializers.DateField(required=False, allow_null=True, default=None)
    end = serializers.DateField(required=False, allow_null=True, default=None)
    client_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    case_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    include_canceled = serializers.BooleanField(required=False, default=False)


class DeskSerializer(serializers.Serializer):
    overdue = TaskSerializer(many=True)
    today = TaskSerializer(many=True)
    upcoming = TaskSerializer(many=True)
    no_date = TaskSerializer(many=True)
    events_today = EventSerializer(many=True)
    events_upcoming = EventSerializer(many=True)

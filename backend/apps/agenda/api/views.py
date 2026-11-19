import uuid
from datetime import datetime, time, timedelta
from typing import Any, cast

from django.db.models import Q, QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.agenda import scheduling, services
from apps.agenda.models import Event, Task
from apps.core import audit
from apps.core.views_base import schema_safe_queryset

from .serializers import (
    DeskSerializer,
    EventFilterSerializer,
    EventSerializer,
    TaskFilterSerializer,
    TaskSerializer,
)

_TASK_RELATED = ("assignee", "client", "legal_case", "completed_by")
_EVENT_RELATED = ("responsible", "client", "legal_case")


@extend_schema(tags=["agenda"])
class TaskViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Tarefas e prazos. Sem DELETE: cancele (status=CANCELED)."""

    serializer_class = TaskSerializer

    def get_queryset(self) -> QuerySet[Task]:
        fake = schema_safe_queryset(self, Task)
        if fake is not None:
            return fake
        qs = Task.objects.select_related(*_TASK_RELATED)
        if self.action != "list":
            return qs
        f = TaskFilterSerializer(data=self.request.query_params)
        f.is_valid(raise_exception=True)
        data = f.validated_data
        if data["status"]:
            qs = qs.filter(status=data["status"])
        assignee = data["assignee"]
        if assignee == "me":
            qs = qs.filter(assignee=self.request.user)
        elif assignee == "none":
            qs = qs.filter(assignee__isnull=True)
        elif assignee:
            try:
                qs = qs.filter(assignee_id=uuid.UUID(assignee))
            except ValueError:
                qs = qs.none()
        day = services.today()
        due = data["due"]
        if due == "overdue":
            qs = qs.filter(due_date__lt=day, status=Task.Status.OPEN)
        elif due == "today":
            qs = qs.filter(due_date=day)
        elif due == "week":
            qs = qs.filter(due_date__gte=day, due_date__lte=day + timedelta(days=7))
        elif due == "none":
            qs = qs.filter(due_date__isnull=True)
        if data["client_id"]:
            qs = qs.filter(client_id=data["client_id"])
        if data["case_id"]:
            qs = qs.filter(legal_case_id=data["case_id"])
        if data["q"].strip():
            q = data["q"].strip()
            qs = qs.filter(
                Q(title__icontains=q) | Q(description__icontains=q) | Q(client__name__icontains=q)
            )
        # Abertas primeiro; dentro delas, por data (sem data por último).
        return qs.order_by("status", "due_date", "due_time", "-created_at")

    @extend_schema(parameters=[TaskFilterSerializer])
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer: BaseSerializer[Task]) -> None:
        task = serializer.save(created_by=self.request.user)
        audit.record(
            "task.created",
            task,
            actor_type=audit.Actor.USER,
            actor_user=self.request.user,
            data={"kind": task.kind},
        )

    def perform_update(self, serializer: BaseSerializer[Task]) -> None:
        before = cast(Task, serializer.instance).status
        task = serializer.save()
        if before != task.status and task.status == Task.Status.CANCELED:
            audit.record(
                "task.canceled", task, actor_type=audit.Actor.USER, actor_user=self.request.user
            )

    @extend_schema(request=None, responses=TaskSerializer)
    @action(detail=True, methods=["post"])
    def complete(self, request: Request, pk: str | None = None) -> Response:
        task = services.complete_task(self.get_object(), user=cast(User, request.user))
        return Response(TaskSerializer(task).data)

    @extend_schema(request=None, responses=TaskSerializer)
    @action(detail=True, methods=["post"])
    def reopen(self, request: Request, pk: str | None = None) -> Response:
        task = services.reopen_task(self.get_object(), user=cast(User, request.user))
        return Response(TaskSerializer(task).data)


@extend_schema(tags=["agenda"])
class EventViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Agenda (audiências, reuniões, atendimentos). Sem DELETE: cancele."""

    serializer_class = EventSerializer

    def get_queryset(self) -> QuerySet[Event]:
        fake = schema_safe_queryset(self, Event)
        if fake is not None:
            return fake
        qs = Event.objects.select_related(*_EVENT_RELATED)
        if self.action != "list":
            return qs
        f = EventFilterSerializer(data=self.request.query_params)
        f.is_valid(raise_exception=True)
        data = f.validated_data
        tz = services.TZ
        if data["start"]:
            qs = qs.filter(starts_at__gte=datetime.combine(data["start"], time.min, tzinfo=tz))
        if data["end"]:
            end = datetime.combine(data["end"], time.min, tzinfo=tz) + timedelta(days=1)
            qs = qs.filter(starts_at__lt=end)
        if data["client_id"]:
            qs = qs.filter(client_id=data["client_id"])
        if data["case_id"]:
            qs = qs.filter(legal_case_id=data["case_id"])
        if not data["include_canceled"]:
            qs = qs.exclude(status=Event.Status.CANCELED)
        return qs.order_by("starts_at")

    @extend_schema(parameters=[EventFilterSerializer])
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer: BaseSerializer[Event]) -> None:
        event = serializer.save(created_by=self.request.user)
        audit.record(
            "event.created",
            event,
            actor_type=audit.Actor.USER,
            actor_user=self.request.user,
            data={"kind": event.kind},
        )

    def perform_update(self, serializer: BaseSerializer[Event]) -> None:
        instance = cast(Event, serializer.instance)
        before_status, before_start = instance.status, instance.starts_at
        event = serializer.save()
        if event.starts_at != before_start:
            # Remarcou: o lembrete precisa sair de novo para a data nova.
            Event.objects.filter(pk=event.pk).update(client_reminded_at=None)
        if before_status != event.status:
            audit.record(
                f"event.{event.status.lower()}",
                event,
                actor_type=audit.Actor.USER,
                actor_user=self.request.user,
            )

    @extend_schema(request=None, responses=EventSerializer)
    @action(detail=True, methods=["post"])
    def confirm(self, request: Request, pk: str | None = None) -> Response:
        """Confirma o horário pré-reservado pela Vera: o contato recebe a confirmação."""
        event = scheduling.confirm(self.get_object(), user=cast(User, request.user))
        return Response(EventSerializer(event).data)

    @extend_schema(request=None, responses=EventSerializer)
    @action(detail=True, methods=["post"])
    def decline(self, request: Request, pk: str | None = None) -> Response:
        """Recusa a pré-reserva (combine outro horário com o contato pela conversa)."""
        event = scheduling.decline(self.get_object(), user=cast(User, request.user))
        return Response(EventSerializer(event).data)


class MyDeskView(APIView):
    """Minha mesa: atrasadas, hoje, próximos 7 dias e os compromissos."""

    @extend_schema(responses=DeskSerializer, tags=["agenda"])
    def get(self, request: Request) -> Response:
        desk = services.my_desk(cast(User, request.user))
        return Response(DeskSerializer(desk).data)

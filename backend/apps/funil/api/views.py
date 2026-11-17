import uuid
from datetime import timedelta
from typing import Any, cast

from django.db.models import Q, QuerySet
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from apps.accounts.models import User
from apps.clientes.models import Client
from apps.core import audit
from apps.core.views_base import schema_safe_queryset
from apps.funil import services
from apps.funil.models import Opportunity

from .serializers import (
    BoardSummarySerializer,
    MoveSerializer,
    OpportunityFilterSerializer,
    OpportunitySerializer,
)


@extend_schema(tags=["funil"])
class OpportunityViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Funil de novos clientes. Sem DELETE: mova para "Não contratou"."""

    serializer_class = OpportunitySerializer
    pagination_class = None  # o quadro mostra tudo o que está aberto (+ fechadas recentes)

    def get_queryset(self) -> QuerySet[Opportunity]:
        fake = schema_safe_queryset(self, Opportunity)
        if fake is not None:
            return fake
        qs = Opportunity.objects.select_related("client", "owner")
        if self.action != "list":
            return qs
        f = OpportunityFilterSerializer(data=self.request.query_params)
        f.is_valid(raise_exception=True)
        data = f.validated_data
        since = timezone.now() - timedelta(days=data["closed_days"])
        qs = qs.filter(Q(stage__in=Opportunity.OPEN_STAGES) | Q(closed_at__gte=since))
        if data["stage"]:
            qs = qs.filter(stage=data["stage"])
        owner = data["owner"]
        if owner == "me":
            qs = qs.filter(owner=self.request.user)
        elif owner == "none":
            qs = qs.filter(owner__isnull=True)
        elif owner:
            try:
                qs = qs.filter(owner_id=uuid.UUID(owner))
            except ValueError:
                qs = qs.none()
        if data["client_id"]:
            qs = qs.filter(client_id=data["client_id"])
        q = data["q"].strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(client__name__icontains=q))
        return qs.order_by("stage", "position", "-created_at")[:500]

    @extend_schema(parameters=[OpportunityFilterSerializer])
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer: BaseSerializer[Opportunity]) -> None:
        data = dict(serializer.validated_data)
        user = cast(User, self.request.user)
        new_name = data.pop("new_client_name", None)
        new_phone = data.pop("new_client_phone", "")
        if not data.get("client") and new_name:
            client = Client.objects.create(
                name=new_name.strip(), phone_e164=new_phone, status=Client.Status.LEAD
            )
            audit.record(
                "client.lead_created",
                client,
                actor_type=audit.Actor.USER,
                actor_user=user,
                data={"via": "funil"},
            )
            data["client"] = client
        if not data.get("title"):
            data["title"] = f"Caso de {data['client'].name}"
        serializer.instance = services.create_opportunity(user=user, **data)

    def perform_update(self, serializer: BaseSerializer[Opportunity]) -> None:
        data = dict(serializer.validated_data)
        data.pop("new_client_name", None)
        data.pop("new_client_phone", None)
        instance = cast(Opportunity, serializer.instance)
        for field, value in data.items():
            setattr(instance, field, value)
        instance.save()

    @extend_schema(request=MoveSerializer, responses=OpportunitySerializer)
    @action(detail=True, methods=["post"])
    def move(self, request: Request, pk: str | None = None) -> Response:
        payload = MoveSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        opportunity = services.move_opportunity(
            self.get_object(),
            stage=payload.validated_data["stage"],
            position=payload.validated_data.get("position"),
            lost_reason=payload.validated_data.get("lost_reason", ""),
            user=cast(User, request.user),
        )
        return Response(OpportunitySerializer(opportunity).data)

    @extend_schema(responses=BoardSummarySerializer)
    @action(detail=False, methods=["get"])
    def summary(self, request: Request) -> Response:
        return Response(BoardSummarySerializer(services.board_summary()).data)

from typing import Any, cast

from django.db.models import Case, IntegerField, QuerySet, Value, When
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from apps.accounts.authentication import get_membership
from apps.accounts.models import User
from apps.aprovacoes import services
from apps.aprovacoes.models import OutboundDraft
from apps.core.views_base import schema_safe_queryset

from .serializers import (
    ApproveSerializer,
    DraftDetailSerializer,
    DraftFilterSerializer,
    DraftSerializer,
    RejectSerializer,
)


@extend_schema(tags=["aprovacoes"])
class DraftViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Fila de aprovação. Aprovar/rejeitar: OWNER e LAWYER (STAFF se o escritório liberar)."""

    def get_serializer_class(self) -> type[BaseSerializer[Any]]:
        return DraftDetailSerializer if self.action == "retrieve" else DraftSerializer

    def get_queryset(self) -> QuerySet[OutboundDraft]:
        fake = schema_safe_queryset(self, OutboundDraft)
        if fake is not None:
            return fake
        qs = OutboundDraft.objects.select_related(
            "conversation", "client", "source_message", "sent_message", "decided_by", "generation"
        )
        if self.action == "list":
            filters = DraftFilterSerializer(data=self.request.query_params)
            filters.is_valid(raise_exception=True)
            if filters.validated_data["status"]:
                qs = qs.filter(status=filters.validated_data["status"])
            if filters.validated_data["conversation_id"]:
                qs = qs.filter(conversation_id=filters.validated_data["conversation_id"])
            # Pendentes: urgentes primeiro, depois os mais antigos (fila). Demais: recentes.
            if filters.validated_data["status"] == OutboundDraft.Status.DRAFT:
                rank = Case(
                    When(urgency="high", then=Value(0)),
                    When(urgency="normal", then=Value(1)),
                    default=Value(2),
                    output_field=IntegerField(),
                )
                return qs.annotate(urgency_rank=rank).order_by("urgency_rank", "created_at")
        return qs.order_by("-created_at")

    @extend_schema(parameters=[DraftFilterSerializer])
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().list(request, *args, **kwargs)

    @extend_schema(request=ApproveSerializer, responses=DraftDetailSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request: Request, pk: str | None = None) -> Response:
        payload = ApproveSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        draft = services.approve_draft(
            draft=self.get_object(),
            user=cast(User, request.user),
            membership=get_membership(request),
            body=payload.validated_data.get("body"),
        )
        return Response(DraftDetailSerializer(draft).data)

    @extend_schema(request=RejectSerializer, responses=DraftDetailSerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request: Request, pk: str | None = None) -> Response:
        payload = RejectSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        draft = services.reject_draft(
            draft=self.get_object(),
            user=cast(User, request.user),
            membership=get_membership(request),
            reason=payload.validated_data["reason"],
        )
        return Response(DraftDetailSerializer(draft).data)

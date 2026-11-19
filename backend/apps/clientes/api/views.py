from typing import Any, cast

from django.db.models import Count, QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from apps.accounts.authentication import get_membership
from apps.accounts.models import User
from apps.clientes import selectors, services
from apps.clientes.models import Client, Tag
from apps.clientes.timeline import client_timeline
from apps.core import audit, trash
from apps.core.views_base import schema_safe_queryset

from .serializers import (
    ClientFilterSerializer,
    ClientNoteSerializer,
    ClientSerializer,
    TagSerializer,
    TermAcceptanceSerializer,
    TimelineQuerySerializer,
    TimelineSerializer,
)


@extend_schema(tags=["clientes"])
class ClientViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Clientes do escritório. DELETE manda para a lixeira (restaurável por 30 dias).

    Com parcelas em aberto, o DELETE devolve 409 `has_open_installments`; repita com
    `?force=1` para confirmar.
    """

    serializer_class = ClientSerializer

    def get_queryset(self) -> QuerySet[Client]:
        fake = schema_safe_queryset(self, Client)
        if fake is not None:
            return fake
        if self.action == "list":
            filters = ClientFilterSerializer(data=self.request.query_params)
            filters.is_valid(raise_exception=True)
            return selectors.search_clients(**filters.validated_data)
        return selectors.clients_with_tags()

    @extend_schema(parameters=[ClientFilterSerializer])
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer: BaseSerializer[Client]) -> None:
        data = dict(serializer.validated_data)
        tags = data.pop("tag_ids", None)
        client = services.create_client(tags=tags, **data)
        serializer.instance = selectors.clients_with_tags().get(pk=client.pk)

    def perform_update(self, serializer: BaseSerializer[Client]) -> None:
        data = dict(serializer.validated_data)
        tags = data.pop("tag_ids", None)
        client = services.update_client(cast(Client, serializer.instance), tags=tags, **data)
        # Recarrega para a resposta trazer as etiquetas novas (o prefetch antigo ficou velho).
        serializer.instance = selectors.clients_with_tags().get(pk=client.pk)

    @extend_schema(parameters=[OpenApiParameter("force", bool, required=False)])
    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        trash.require_can_remove(get_membership(request))
        force = request.query_params.get("force") in ("1", "true")
        trash.trash_client(self.get_object(), user=cast(User, request.user), force=force)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(responses=TermAcceptanceSerializer(many=True))
    @action(detail=True, methods=["get"], url_path="term-acceptances")
    def term_acceptances(self, request: Request, pk: str | None = None) -> Response:
        client = self.get_object()
        data = TermAcceptanceSerializer(selectors.term_acceptances(client), many=True).data
        return Response(data)

    @extend_schema(request=TermAcceptanceSerializer, responses={201: TermAcceptanceSerializer})
    @term_acceptances.mapping.post
    def register_term_acceptance(self, request: Request, pk: str | None = None) -> Response:
        client = self.get_object()
        payload = TermAcceptanceSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        acceptance = services.register_term_acceptance(
            client=client,
            recorded_by=request.user,  # type: ignore[arg-type]
            **payload.validated_data,
        )
        return Response(TermAcceptanceSerializer(acceptance).data, status=status.HTTP_201_CREATED)

    @extend_schema(parameters=[TimelineQuerySerializer], responses=TimelineSerializer)
    @action(detail=True, methods=["get"])
    def timeline(self, request: Request, pk: str | None = None) -> Response:
        """Ficha 360°: atendimentos, tarefas, agenda, WhatsApp, processos e andamentos."""
        query = TimelineQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        items, next_before = client_timeline(self.get_object(), **query.validated_data)
        return Response(TimelineSerializer({"results": items, "next_before": next_before}).data)

    @extend_schema(request=ClientNoteSerializer, responses={201: ClientNoteSerializer})
    @action(detail=True, methods=["post"])
    def notes(self, request: Request, pk: str | None = None) -> Response:
        """Registrar atendimento (ligação, reunião, anotação)."""
        client = self.get_object()
        payload = ClientNoteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        note = payload.save(client=client, author=request.user)
        audit.record(
            "client.note_added",
            note,
            actor_type=audit.Actor.USER,
            actor_user=request.user,
            data={"client_id": str(client.pk), "kind": note.kind},
        )
        return Response(ClientNoteSerializer(note).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["clientes"])
class TagViewSet(viewsets.ModelViewSet):
    """Etiquetas do escritório. Apagar tira a etiqueta dos clientes (não apaga clientes)."""

    serializer_class = TagSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[Tag]:
        fake = schema_safe_queryset(self, Tag)
        if fake is not None:
            return fake
        return Tag.objects.annotate(client_count=Count("client_tags")).order_by("name")

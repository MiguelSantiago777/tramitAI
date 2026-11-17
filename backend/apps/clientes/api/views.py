from typing import Any, cast

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from apps.clientes import selectors, services
from apps.clientes.models import Client
from apps.core.views_base import schema_safe_queryset

from .serializers import ClientFilterSerializer, ClientSerializer, TermAcceptanceSerializer


@extend_schema(tags=["clientes"])
class ClientViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Clientes do escritório. Sem DELETE: para tirar de circulação, use status ARCHIVED.

    Exclusão definitiva (pedido LGPD) será um fluxo próprio, com anonimização.
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
        return Client.objects.all()

    @extend_schema(parameters=[ClientFilterSerializer])
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer: BaseSerializer[Client]) -> None:
        serializer.instance = services.create_client(**serializer.validated_data)

    def perform_update(self, serializer: BaseSerializer[Client]) -> None:
        serializer.instance = services.update_client(
            cast(Client, serializer.instance), **serializer.validated_data
        )

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

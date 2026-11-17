from typing import Any, cast

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from apps.core.views_base import schema_safe_queryset
from apps.processos import selectors, services
from apps.processos.models import LegalCase

from .serializers import CaseFilterSerializer, LegalCaseSerializer


def _links(data: dict[str, Any]) -> list[services.ClientLink] | None:
    items = data.pop("case_clients", None)
    if items is None:
        return None
    return [services.ClientLink(client=i["client"], role=i["role"]) for i in items]


@extend_schema(tags=["processos"])
class LegalCaseViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Processos do escritório. Sem DELETE: arquive com status ARCHIVED."""

    serializer_class = LegalCaseSerializer

    def get_queryset(self) -> QuerySet[LegalCase]:
        fake = schema_safe_queryset(self, LegalCase)
        if fake is not None:
            return fake
        if self.action == "list":
            filters = CaseFilterSerializer(data=self.request.query_params)
            filters.is_valid(raise_exception=True)
            return selectors.search_cases(**filters.validated_data)
        return selectors.cases_with_relations()

    @extend_schema(parameters=[CaseFilterSerializer])
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer: BaseSerializer[LegalCase]) -> None:
        data = dict(serializer.validated_data)
        serializer.instance = services.create_case(links=_links(data) or [], **data)

    def perform_update(self, serializer: BaseSerializer[LegalCase]) -> None:
        data = dict(serializer.validated_data)
        serializer.instance = services.update_case(
            cast(LegalCase, serializer.instance), links=_links(data), **data
        )

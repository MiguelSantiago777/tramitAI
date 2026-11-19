"""API da Lixeira: lista, restaura e apaga de vez clientes e processos removidos."""

from datetime import datetime
from typing import Any, cast

from django.db.models import Model
from django.urls import path
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import get_membership
from apps.accounts.models import User
from apps.accounts.permissions import IsTenantOwner

from . import trash

TrashItem = inline_serializer(
    "TrashItem",
    {
        "kind": serializers.ChoiceField(choices=["client", "case"]),
        "id": serializers.UUIDField(),
        "label": serializers.CharField(),
        "detail": serializers.CharField(),
        "deleted_at": serializers.DateTimeField(),
        "deleted_by_name": serializers.CharField(),
        "purge_at": serializers.DateTimeField(),
    },
    many=True,
)


def _model(kind: str) -> Any:
    from apps.clientes.models import Client
    from apps.processos.models import LegalCase

    if kind == "client":
        return Client
    if kind == "case":
        return LegalCase
    raise NotFound()


def _trashed(kind: str, pk: str) -> Model:
    qs = _model(kind).with_deleted.filter(pk=pk, deleted_at__isnull=False)
    if kind == "client":
        qs = qs.filter(anonymized_at__isnull=True)
    obj = qs.first()
    if obj is None:
        raise NotFound()
    return cast(Model, obj)


def _who(user: User | None) -> str:
    return (user.full_name or user.email) if user else ""


def _item(kind: str, obj: Any, label: str, detail: str) -> dict[str, Any]:
    deleted_at = cast(datetime, obj.deleted_at)
    return {
        "kind": kind,
        "id": obj.pk,
        "label": label,
        "detail": detail,
        "deleted_at": deleted_at,
        "deleted_by_name": _who(obj.deleted_by),
        "purge_at": deleted_at + trash.RETENTION,
    }


class TrashListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["lixeira"], responses=TrashItem)
    def get(self, request: Request) -> Response:
        """Clientes e processos na lixeira (mais recentes primeiro)."""
        client_model, case_model = _model("client"), _model("case")
        items = [
            _item("client", c, c.name, c.get_status_display())
            for c in client_model.with_deleted.filter(
                deleted_at__isnull=False, anonymized_at__isnull=True
            ).select_related("deleted_by")
        ] + [
            _item("case", c, c.cnj_formatted, c.classe or c.tribunal_label)
            for c in case_model.with_deleted.filter(deleted_at__isnull=False).select_related(
                "deleted_by"
            )
        ]
        items.sort(key=lambda i: i["deleted_at"], reverse=True)
        return Response(items)


class TrashRestoreView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["lixeira"], request=None, responses={204: None})
    def post(self, request: Request, kind: str, pk: str) -> Response:
        """Tira da lixeira (volta para as listas como estava)."""
        trash.require_can_remove(get_membership(request))
        trash.restore(_trashed(kind, pk), user=cast(User, request.user))
        return Response(status=status.HTTP_204_NO_CONTENT)


class TrashPurgeView(APIView):
    permission_classes = [IsAuthenticated, IsTenantOwner]

    @extend_schema(tags=["lixeira"], responses={204: None})
    def delete(self, request: Request, kind: str, pk: str) -> Response:
        """Apaga de vez, sem esperar os 30 dias. Só o titular. Não tem volta."""
        obj = _trashed(kind, pk)
        user = cast(User, request.user)
        if kind == "client":
            trash.purge_client(obj, user=user)
        else:
            trash.purge_case(obj, user=user)
        return Response(status=status.HTTP_204_NO_CONTENT)


urlpatterns = [
    path("trash/", TrashListView.as_view(), name="trash"),
    path("trash/<str:kind>/<uuid:pk>/restore/", TrashRestoreView.as_view(), name="trash-restore"),
    path("trash/<str:kind>/<uuid:pk>/", TrashPurgeView.as_view(), name="trash-purge"),
]

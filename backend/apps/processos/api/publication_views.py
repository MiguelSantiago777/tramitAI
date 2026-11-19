from typing import Any, cast

from django.db import transaction
from django.db.models import Count, Q, QuerySet
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from apps.accounts.models import User
from apps.core import audit
from apps.core.br import only_digits
from apps.core.tenancy import get_current_tenant_id
from apps.core.views_base import schema_safe_queryset
from apps.processos import publications
from apps.processos.models import MonitoredOab, Publication

from .publication_serializers import (
    MonitoredOabSerializer,
    PublicationFilterSerializer,
    PublicationSerializer,
    PublicationStatusSerializer,
)


class _PlanGated(viewsets.GenericViewSet):
    """Publicações do Diário só nos planos que incluem (402 com mensagem para a tela)."""

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        if not getattr(self, "swagger_fake_view", False):
            publications.require_feature(get_current_tenant_id())


@extend_schema(tags=["publicacoes"])
class MonitoredOabViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    _PlanGated,
):
    """OABs cujas publicações no Diário (DJEN) o escritório acompanha."""

    serializer_class = MonitoredOabSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self) -> QuerySet[MonitoredOab]:
        fake = schema_safe_queryset(self, MonitoredOab)
        if fake is not None:
            return fake
        return (
            MonitoredOab.objects.select_related("user")
            .annotate(
                new_publication_count=Count(
                    "publications", filter=Q(publications__status=Publication.Status.NEW)
                )
            )
            .order_by("uf", "number")
        )

    def perform_create(self, serializer: BaseSerializer[MonitoredOab]) -> None:
        # Sem usuário escolhido: as tarefas das publicações vão para quem cadastrou.
        extra = {} if "user" in serializer.validated_data else {"user": self.request.user}
        oab = serializer.save(**extra)
        audit.record("oab.created", oab, actor_type=audit.Actor.USER, actor_user=self.request.user)
        # Primeira busca já na hora: o advogado vê o resultado sem esperar o ciclo de 2h.
        from apps.processos.tasks import sync_oab_task

        args = [str(oab.tenant_id), str(oab.pk)]
        transaction.on_commit(lambda: sync_oab_task.apply_async(args=args))

    def perform_destroy(self, instance: MonitoredOab) -> None:
        audit.record(
            "oab.deleted", instance, actor_type=audit.Actor.USER, actor_user=self.request.user
        )
        instance.delete()

    @extend_schema(request=None, responses={202: None})
    @action(detail=True, methods=["post"])
    def check(self, request: Request, pk: str | None = None) -> Response:
        """Busca as publicações agora (fila; o resultado aparece em alguns segundos)."""
        publications.request_check(self.get_object(), user=cast(User, request.user))
        return Response(status=status.HTTP_202_ACCEPTED)


@extend_schema(tags=["publicacoes"])
class PublicationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, _PlanGated):
    """Publicações do Diário (intimações, citações...) das OABs monitoradas."""

    serializer_class = PublicationSerializer

    def get_queryset(self) -> QuerySet[Publication]:
        fake = schema_safe_queryset(self, Publication)
        if fake is not None:
            return fake
        qs = Publication.objects.select_related("oab", "handled_by")
        if self.action != "list":
            return qs
        filters = PublicationFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        data = filters.validated_data
        if data["status"]:
            qs = qs.filter(status=data["status"])
        if data["case_id"]:
            qs = qs.filter(legal_case_id=data["case_id"])
        q = data["q"].strip()
        if q:
            condition = Q(orgao__icontains=q) | Q(kind__icontains=q) | Q(classe__icontains=q)
            digits = only_digits(q)
            if len(digits) >= 4:
                condition |= Q(cnj_number__contains=digits)
            qs = qs.filter(condition)
        return qs.order_by("-available_on", "-djen_id")

    @extend_schema(parameters=[PublicationFilterSerializer])
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().list(request, *args, **kwargs)

    @extend_schema(request=PublicationStatusSerializer, responses=PublicationSerializer)
    @action(detail=True, methods=["post"])
    def mark(self, request: Request, pk: str | None = None) -> Response:
        """Marca como tratada, ignorada ou volta para nova."""
        body = PublicationStatusSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        publication = publications.set_status(
            self.get_object(), body.validated_data["status"], user=cast(User, request.user)
        )
        return Response(PublicationSerializer(publication).data)

    @extend_schema(
        request=None,
        responses=inline_serializer("CaseFromPublication", {"case_id": serializers.UUIDField()}),
    )
    @action(detail=True, methods=["post"], url_path="create-case")
    def create_case(self, request: Request, pk: str | None = None) -> Response:
        """Cadastra o processo desta publicação (ou devolve o que já existe)."""
        case = publications.create_case_from(self.get_object(), user=cast(User, request.user))
        return Response({"case_id": str(case.pk)})

    @extend_schema(
        responses=inline_serializer("PublicationSummary", {"new": serializers.IntegerField()})
    )
    @action(detail=False, methods=["get"])
    def summary(self, request: Request) -> Response:
        """Quantas publicações novas (para o contador do menu)."""
        return Response({"new": Publication.objects.filter(status=Publication.Status.NEW).count()})

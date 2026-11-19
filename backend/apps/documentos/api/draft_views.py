from typing import Any, cast

from django.db import transaction
from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.serializers import BaseSerializer

from apps.accounts.models import User
from apps.clientes.models import Client
from apps.core import audit
from apps.core.exceptions import ApiError
from apps.core.serializers import TenantScopedPrimaryKeyRelatedField
from apps.core.views_base import schema_safe_queryset
from apps.documentos.models import DocumentDraft
from apps.financeiro.models import FeeAgreement
from apps.processos.models import LegalCase


class DocumentDraftSerializer(serializers.ModelSerializer):
    client_id = TenantScopedPrimaryKeyRelatedField(
        model=Client, source="client", required=False, allow_null=True
    )
    legal_case_id = TenantScopedPrimaryKeyRelatedField(
        model=LegalCase, source="legal_case", required=False, allow_null=True
    )
    fee_agreement_id = TenantScopedPrimaryKeyRelatedField(
        model=FeeAgreement, source="fee_agreement", required=False, allow_null=True
    )
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    docx_id = serializers.UUIDField(read_only=True, allow_null=True)
    pdf_id = serializers.UUIDField(read_only=True, allow_null=True)
    instructions = serializers.CharField(max_length=6000, write_only=True)

    class Meta:
        model = DocumentDraft
        fields = [
            "id",
            "kind",
            "kind_label",
            "title",
            "instructions",
            "client_id",
            "legal_case_id",
            "fee_agreement_id",
            "status",
            "error_code",
            "review_notes",
            "missing_fields",
            "docx_id",
            "pdf_id",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "error_code",
            "review_notes",
            "missing_fields",
            "created_at",
        ]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        client, case = attrs.get("client"), attrs.get("legal_case")
        agreement = attrs.get("fee_agreement")
        if client is None and case is None and agreement is not None:
            attrs["client"] = client = agreement.client
        if client is None and case is None:
            raise serializers.ValidationError(
                {"client_id": ["Escolha o cliente ou o processo: a minuta vai para a pasta dele."]}
            )
        if client is None and case is not None:
            # Processo sem cliente escolhido: usa o primeiro cliente do processo.
            link = case.case_clients.select_related("client").order_by("created_at").first()
            attrs["client"] = link.client if link else None
        if agreement is not None and attrs.get("client") not in (None, agreement.client):
            raise serializers.ValidationError(
                {"fee_agreement_id": ["Estes honorários são de outro cliente."]}
            )
        if agreement is not None and attrs.get("client") is None:
            attrs["client"] = agreement.client
        return attrs


class DraftFilterSerializer(serializers.Serializer):
    client_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    case_id = serializers.UUIDField(required=False, allow_null=True, default=None)


@extend_schema(tags=["documentos"])
class DocumentDraftViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """Minutas escritas pela Lia. POST devolve 201 "Escrevendo"; consulte até ficar pronta."""

    serializer_class = DocumentDraftSerializer

    def get_queryset(self) -> QuerySet[DocumentDraft]:
        fake = schema_safe_queryset(self, DocumentDraft)
        if fake is not None:
            return fake
        qs = DocumentDraft.objects.all()
        if self.action == "list":
            f = DraftFilterSerializer(data=self.request.query_params)
            f.is_valid(raise_exception=True)
            if f.validated_data["client_id"]:
                qs = qs.filter(client_id=f.validated_data["client_id"])
            if f.validated_data["case_id"]:
                qs = qs.filter(legal_case_id=f.validated_data["case_id"])
        return qs.order_by("-created_at")

    def perform_create(self, serializer: BaseSerializer[DocumentDraft]) -> None:
        from apps.cobranca.limits import ai_allowed
        from apps.ia.tasks import write_legal_draft

        draft = serializer.save(created_by=self.request.user)
        if not ai_allowed(draft.tenant_id):
            raise ApiError(
                "A Lia já usou todas as mensagens do plano neste mês. Mude de plano em "
                "Assinatura para continuar.",
                code="ai_limit",
                status_code=402,
            )
        audit.record(
            "draft.requested",
            draft,
            actor_type=audit.Actor.USER,
            actor_user=cast(User, self.request.user),
            data={"kind": draft.kind},
        )
        args = [str(draft.tenant_id), str(draft.pk)]
        transaction.on_commit(lambda: write_legal_draft.apply_async(args=args))

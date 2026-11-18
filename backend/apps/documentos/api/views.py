from typing import Any, cast

from django.db.models import QuerySet
from django.http import FileResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.authentication import get_membership
from apps.accounts.models import User
from apps.clientes.models import Client
from apps.core import audit
from apps.core.views_base import schema_safe_queryset
from apps.documentos import services
from apps.documentos.models import Document

from .serializers import DocumentFilterSerializer, DocumentSerializer, DocumentUploadSerializer


@extend_schema(tags=["documentos"])
class DocumentViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Documentos do escritório. Download só por aqui (com login); nunca há link público."""

    serializer_class = DocumentSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self) -> QuerySet[Document]:
        fake = schema_safe_queryset(self, Document)
        if fake is not None:
            return fake
        qs = Document.objects.select_related(
            "client", "legal_case", "conversation__client", "uploaded_by"
        )
        if self.action != "list":
            return qs
        f = DocumentFilterSerializer(data=self.request.query_params)
        f.is_valid(raise_exception=True)
        data = f.validated_data
        if data.get("client"):
            client = Client.objects.filter(pk=data["client"]).first()
            qs = qs.filter(pk__in=services.for_client(client).values("pk")) if client else qs.none()
        if data.get("legal_case"):
            qs = qs.filter(legal_case_id=data["legal_case"])
        if data.get("conversation"):
            qs = qs.filter(conversation_id=data["conversation"])
        if data.get("category"):
            qs = qs.filter(category=data["category"])
        if data["q"].strip():
            qs = qs.filter(name__icontains=data["q"].strip())
        return qs.order_by("-created_at")

    @extend_schema(parameters=[DocumentFilterSerializer])
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().list(request, *args, **kwargs)

    @extend_schema(request=DocumentUploadSerializer, responses={201: DocumentSerializer})
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        payload = DocumentUploadSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        document = services.create_upload(
            upload=data["file"],
            user=cast(User, request.user),
            client=data.get("client"),
            legal_case=data.get("legal_case"),
            category=data["category"],
            description=data.get("description", ""),
        )
        return Response(DocumentSerializer(document).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer: Any) -> None:
        document = serializer.save()
        audit.record(
            "document.updated",
            document,
            actor_type=audit.Actor.USER,
            actor_user=cast(User, self.request.user),
            data={"fields": sorted(serializer.validated_data.keys())},
        )

    def perform_destroy(self, instance: Document) -> None:
        services.delete_document(
            instance, user=cast(User, self.request.user), membership=get_membership(self.request)
        )

    @extend_schema(
        parameters=[OpenApiParameter("inline", OpenApiTypes.BOOL, required=False)],
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY},
    )
    @action(detail=True, methods=["get"])
    def download(self, request: Request, pk: str | None = None) -> FileResponse:
        document = self.get_object()
        inline = request.query_params.get("inline") in ("1", "true") and (
            document.content_type in services.INLINE_TYPES
        )
        if not inline:
            audit.record(
                "document.downloaded",
                document,
                actor_type=audit.Actor.USER,
                actor_user=cast(User, request.user),
            )
        response = FileResponse(
            document.file.open("rb"),
            as_attachment=not inline,
            filename=document.name,
            content_type=document.content_type if inline else "application/octet-stream",
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        response["Cache-Control"] = "private, no-store"
        return response

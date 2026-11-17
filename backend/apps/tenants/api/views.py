from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsOwnerForWrites
from apps.accounts.selectors import tenant_members
from apps.core.exceptions import ApiError
from apps.core.tenancy import get_current_tenant_id
from apps.tenants import services
from apps.tenants.models import ClientTermVersion, TenantSettings

from .serializers import ClientTermVersionSerializer, MemberSerializer, TenantSettingsSerializer


class TenantSettingsView(APIView):
    @extend_schema(responses=TenantSettingsSerializer, tags=["tenant"])
    def get(self, request: Request) -> Response:
        settings = get_object_or_404(TenantSettings.objects.all())
        return Response(TenantSettingsSerializer(settings).data)


class MembersView(APIView):
    @extend_schema(responses=MemberSerializer(many=True), tags=["tenant"])
    def get(self, request: Request) -> Response:
        members = tenant_members(tenant_id=get_current_tenant_id())
        return Response(MemberSerializer(members, many=True).data)


class ClientTermView(APIView):
    """Termo de ciência de IA vigente. Publicar nova versão: só o titular."""

    permission_classes = [IsOwnerForWrites]

    @extend_schema(responses=ClientTermVersionSerializer, tags=["tenant"])
    def get(self, request: Request) -> Response:
        term = services.active_term_version()
        if term is None:
            raise ApiError(
                "Nenhum termo publicado.",
                code="no_active_term",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return Response(ClientTermVersionSerializer(term).data)

    @extend_schema(
        request=ClientTermVersionSerializer,
        responses={201: ClientTermVersionSerializer},
        tags=["tenant"],
    )
    def post(self, request: Request) -> Response:
        payload = ClientTermVersionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        term = services.publish_term_version(
            body=payload.validated_data["body"],
            created_by=request.user,  # type: ignore[arg-type]
        )
        return Response(ClientTermVersionSerializer(term).data, status=status.HTTP_201_CREATED)


class ClientTermVersionsView(APIView):
    @extend_schema(responses=ClientTermVersionSerializer(many=True), tags=["tenant"])
    def get(self, request: Request) -> Response:
        versions = ClientTermVersion.objects.select_related("created_by").order_by("-version")
        return Response(ClientTermVersionSerializer(versions, many=True).data)

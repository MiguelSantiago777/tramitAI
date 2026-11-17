from drf_spectacular.utils import extend_schema
from rest_framework.generics import get_object_or_404
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.models import TenantSettings

from .serializers import TenantSettingsSerializer


class TenantSettingsView(APIView):
    @extend_schema(responses=TenantSettingsSerializer, tags=["tenant"])
    def get(self, request: Request) -> Response:
        settings = get_object_or_404(TenantSettings.objects.all())
        return Response(TenantSettingsSerializer(settings).data)

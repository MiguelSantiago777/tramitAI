from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts import services
from apps.accounts.authentication import get_membership
from apps.accounts.models import Membership
from apps.core.tenancy import tenant_context

from .serializers import (
    LoginResponseSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    SessionSerializer,
)


def _session_data(membership: Membership) -> dict[str, Any]:
    return {
        "user": membership.user,
        "tenant": membership.tenant,
        "role": membership.role,
        "can_approve": services.can_approve_drafts(membership),
        "is_platform_admin": bool(membership.user.is_superuser),
    }


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(
        request=LoginSerializer,
        responses=LoginResponseSerializer,
        tags=["auth"],
        description=(
            "Login por e-mail e senha. Se o usuário tiver mais de um escritório e `tenant_id` "
            "não vier, responde 400 com `code=tenant_selection_required` e a lista em "
            "`details.tenants`."
        ),
    )
    def post(self, request: Request) -> Response:
        payload = LoginSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        result = services.login(
            email=payload.validated_data["email"],
            password=payload.validated_data["password"],
            tenant_id=payload.validated_data.get("tenant_id"),
        )
        with tenant_context(result.membership.tenant_id):
            session = _session_data(result.membership)
        return Response(
            LoginResponseSerializer(
                {"access": result.access, "refresh": result.refresh, "session": session}
            ).data
        )


class MeView(APIView):
    @extend_schema(responses=SessionSerializer, tags=["auth"])
    def get(self, request: Request) -> Response:
        return Response(SessionSerializer(_session_data(get_membership(request))).data)


class PasswordResetRequestView(APIView):
    """Pede o e-mail de redefinição. Responde igual exista ou não a conta."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    @extend_schema(request=PasswordResetRequestSerializer, responses={204: None}, tags=["auth"])
    def post(self, request: Request) -> Response:
        payload = PasswordResetRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        services.request_password_reset(payload.validated_data["email"])
        return Response(status=204)


class PasswordResetConfirmView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    @extend_schema(request=PasswordResetConfirmSerializer, responses={204: None}, tags=["auth"])
    def post(self, request: Request) -> Response:
        payload = PasswordResetConfirmSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        services.confirm_password_reset(**payload.validated_data)
        return Response(status=204)

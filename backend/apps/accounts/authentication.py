import uuid
from typing import Any

from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.core.tenancy import activate_tenant

from .models import Membership
from .selectors import active_membership

TENANT_CLAIM = "tid"


class TenantJWTAuthentication(JWTAuthentication):
    """JWT + escritório. Depois de validar o token, confere a Membership e ativa o tenant.

    Roda dentro da transação do request (ATOMIC_REQUESTS), então o set_config local
    vale até o fim do request e morre junto com a transação.
    """

    def authenticate(self, request: Request) -> tuple[Any, Any] | None:
        result = super().authenticate(request)
        if result is None:
            return None
        user, token = result

        try:
            tenant_id = uuid.UUID(str(token.get(TENANT_CLAIM)))
        except ValueError as exc:
            raise AuthenticationFailed(
                "Token sem escritório válido.", code="token_without_tenant"
            ) from exc

        membership = active_membership(user_id=user.pk, tenant_id=tenant_id)
        if membership is None:
            raise AuthenticationFailed("Sem acesso a este escritório.", code="tenant_forbidden")

        activate_tenant(membership.tenant_id)
        request.membership = membership  # type: ignore[attr-defined]
        return user, token


def get_membership(request: Request) -> Membership:
    membership: Membership = request.membership  # type: ignore[attr-defined]
    return membership

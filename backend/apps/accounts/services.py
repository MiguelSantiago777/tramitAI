import uuid
from dataclasses import dataclass

from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.exceptions import ApiError
from apps.tenants.models import TenantSettings

from .authentication import TENANT_CLAIM
from .models import Membership, User, normalize_email_address
from .selectors import active_memberships


@dataclass(frozen=True)
class LoginResult:
    access: str
    refresh: str
    membership: Membership


def login(*, email: str, password: str, tenant_id: uuid.UUID | None) -> LoginResult:
    """Valida credenciais, escolhe o escritório e emite o par de tokens com o claim `tid`.

    Com mais de um escritório e sem `tenant_id`, devolve erro `tenant_selection_required`
    com a lista para o frontend perguntar ao usuário.
    """
    user = authenticate(username=normalize_email_address(email), password=password)
    if not isinstance(user, User):
        raise ApiError(
            "E-mail ou senha inválidos.",
            code="invalid_credentials",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    memberships = list(active_memberships(user_id=user.id))
    if not memberships:
        raise ApiError(
            "Seu usuário não está vinculado a nenhum escritório ativo.",
            code="no_active_tenant",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    if tenant_id is not None:
        chosen = next((m for m in memberships if m.tenant_id == tenant_id), None)
        if chosen is None:
            raise ApiError(
                "Sem acesso a este escritório.",
                code="tenant_forbidden",
                status_code=status.HTTP_403_FORBIDDEN,
            )
    elif len(memberships) == 1:
        chosen = memberships[0]
    else:
        raise ApiError(
            "Escolha o escritório.",
            code="tenant_selection_required",
            details={
                "tenants": [{"id": str(m.tenant_id), "name": m.tenant.name} for m in memberships]
            },
        )

    refresh = RefreshToken.for_user(user)
    refresh[TENANT_CLAIM] = str(chosen.tenant_id)
    return LoginResult(access=str(refresh.access_token), refresh=str(refresh), membership=chosen)


def can_approve_drafts(membership: Membership) -> bool:
    """OWNER e LAWYER sempre; STAFF só se o escritório liberar. Requer tenant ativo."""
    if membership.role in (Membership.Role.OWNER, Membership.Role.LAWYER):
        return True
    settings = TenantSettings.objects.first()
    return bool(settings and settings.staff_can_approve)

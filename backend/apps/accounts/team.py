"""Equipe do escritório: convidar, mudar papel, desativar.

Regras:
- Só o titular (OWNER) mexe na equipe (permissão na view).
- O escritório nunca fica sem titular ativo.
- Ninguém altera o próprio vínculo (evita se trancar para fora por engano).
- Convite = usuário sem senha + e-mail com link para criar a senha (vale 3 dias, uso único).
"""

import uuid
from dataclasses import dataclass

from django.db import transaction
from rest_framework import status

from apps.core.exceptions import ApiError

from .models import Membership, User, normalize_email_address


@dataclass(frozen=True)
class TeamMember:
    membership: Membership
    pending: bool  # convidado que ainda não criou a senha


def team(tenant_id: uuid.UUID) -> list[TeamMember]:
    memberships = (
        Membership.objects.select_related("user")
        .filter(tenant_id=tenant_id)
        .order_by("-is_active", "user__full_name", "user__email")
    )
    return [TeamMember(m, pending=not m.user.has_usable_password()) for m in memberships]


def invite_member(
    *, tenant_id: uuid.UUID, email: str, full_name: str, role: str, invited_by: User
) -> Membership:
    from .tasks import send_invite_email

    email = normalize_email_address(email)
    user = User.objects.filter(email__iexact=email).first()
    if user is None:
        user = User.objects.create_user(email=email, password=None, full_name=full_name.strip())
    membership = Membership.objects.filter(user=user, tenant_id=tenant_id).first()
    if membership is not None and membership.is_active:
        raise ApiError(
            "Essa pessoa já faz parte da equipe.",
            code="already_member",
            status_code=status.HTTP_409_CONFLICT,
        )
    from apps.cobranca.limits import check_can_add_user

    check_can_add_user(tenant_id)
    if membership is None:
        membership = Membership.objects.create(user=user, tenant_id=tenant_id, role=role)
    else:
        membership.role = role
        membership.is_active = True
        membership.save(update_fields=["role", "is_active"])

    membership_id = str(membership.pk)
    invited_by_name = invited_by.full_name or invited_by.email
    transaction.on_commit(lambda: send_invite_email.delay(membership_id, invited_by_name))
    return membership


def resend_invite(membership: Membership, *, invited_by: User) -> None:
    from .tasks import send_invite_email

    if membership.user.has_usable_password():
        raise ApiError(
            "Essa pessoa já criou a senha. Se esqueceu, use 'Esqueci minha senha' no login.",
            code="already_active",
            status_code=status.HTTP_409_CONFLICT,
        )
    membership_id = str(membership.pk)
    invited_by_name = invited_by.full_name or invited_by.email
    transaction.on_commit(lambda: send_invite_email.delay(membership_id, invited_by_name))


def update_member(
    membership: Membership, *, actor: User, role: str | None, is_active: bool | None
) -> Membership:
    if membership.user_id == actor.pk:
        raise ApiError(
            "Você não pode alterar o seu próprio acesso. Peça a outro titular.",
            code="cannot_change_self",
            status_code=status.HTTP_409_CONFLICT,
        )
    new_role = role if role is not None else membership.role
    new_active = is_active if is_active is not None else membership.is_active
    loses_owner = membership.role == Membership.Role.OWNER and membership.is_active
    if loses_owner and (new_role != Membership.Role.OWNER or not new_active):
        others = (
            Membership.objects.filter(
                tenant_id=membership.tenant_id, role=Membership.Role.OWNER, is_active=True
            )
            .exclude(pk=membership.pk)
            .exists()
        )
        if not others:
            raise ApiError(
                "O escritório precisa de pelo menos um titular ativo.",
                code="last_owner",
                status_code=status.HTTP_409_CONFLICT,
            )
    if new_active and not membership.is_active:
        from apps.cobranca.limits import check_can_add_user

        check_can_add_user(membership.tenant_id)  # reativar ocupa um lugar do plano
    membership.role = new_role
    membership.is_active = new_active
    membership.save(update_fields=["role", "is_active"])
    return membership


def invite_link(user: User) -> str:
    """Mesmo link de criar senha; `convite=1` só muda o texto da tela."""
    from .services import password_reset_link

    return password_reset_link(user) + "&convite=1"

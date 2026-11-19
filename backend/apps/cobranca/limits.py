"""Limites do plano: usuários e mensagens da Vera por mês.

Isento ou sem plano = sem limite. Limite vazio no plano = sem limite.
Ao atingir o limite da Vera, ela para de escrever até o mês virar; o atendimento continua
(mensagens chegam e a equipe responde à mão).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.utils import timezone
from rest_framework import status as http_status

from apps.accounts.models import Membership
from apps.core.exceptions import ApiError

from .models import Plan, Subscription

TZ = ZoneInfo("America/Sao_Paulo")
WARN_AT = 0.8


@dataclass(frozen=True)
class Usage:
    users_used: int
    users_limit: int | None
    ai_used: int
    ai_limit: int | None

    @property
    def ai_exhausted(self) -> bool:
        return self.ai_limit is not None and self.ai_used >= self.ai_limit

    @property
    def ai_warning(self) -> bool:
        return self.ai_limit is not None and self.ai_used >= self.ai_limit * WARN_AT


def plan_for(tenant_id: uuid.UUID) -> Plan | None:
    sub = Subscription.objects.select_related("plan").filter(tenant_id=tenant_id).first()
    if sub is None or sub.status == Subscription.Status.EXEMPT:
        return None
    return sub.plan


def month_start(now: datetime | None = None) -> datetime:
    local = (now or timezone.now()).astimezone(TZ)
    return datetime.combine(local.date().replace(day=1), time.min, tzinfo=TZ)


def users_used(tenant_id: uuid.UUID) -> int:
    """Lugares ocupados: membros ativos (inclui convite ainda não aceito)."""
    return Membership.objects.filter(tenant_id=tenant_id, is_active=True).count()


def ai_used(tenant_id: uuid.UUID) -> int:
    """Respostas que a Vera escreveu no mês (tenant ativo). Falha do provedor não conta."""
    from apps.ia.models import AiGeneration

    return AiGeneration.objects.filter(
        created_at__gte=month_start(), status=AiGeneration.Status.OK
    ).count()


def usage(tenant_id: uuid.UUID) -> Usage:
    plan = plan_for(tenant_id)
    return Usage(
        users_used=users_used(tenant_id),
        users_limit=plan.max_users if plan else None,
        ai_used=ai_used(tenant_id),
        ai_limit=plan.monthly_ai_limit if plan else None,
    )


def check_can_add_user(tenant_id: uuid.UUID) -> None:
    plan = plan_for(tenant_id)
    if plan is None or plan.max_users is None:
        return
    if users_used(tenant_id) >= plan.max_users:
        raise ApiError(
            f"O plano {plan.name} permite até {plan.max_users} usuário(s). Para convidar mais "
            "pessoas, mude de plano em Assinatura.",
            code="plan_user_limit",
            status_code=http_status.HTTP_402_PAYMENT_REQUIRED,
        )


def ai_allowed(tenant_id: uuid.UUID) -> bool:
    """A Vera ainda pode escrever neste mês? (tenant ativo)"""
    plan = plan_for(tenant_id)
    if plan is None or plan.monthly_ai_limit is None:
        return True
    return ai_used(tenant_id) < plan.monthly_ai_limit

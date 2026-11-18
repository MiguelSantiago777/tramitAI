"""Painel da plataforma (só o dono do TramitAI): assinaturas, receita e gestão dos escritórios.

Mostra só dados da plataforma (escritório, assinatura, plano, pagamentos) e contagens de uso.
Nunca o conteúdo dos escritórios (conversas, clientes, processos): sigilo e LGPD.
Cada ação fica na trilha de auditoria do escritório afetado.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import status as http_status

from apps.accounts.models import Membership, User
from apps.core import audit
from apps.core.exceptions import ApiError
from apps.core.tenancy import tenant_context
from apps.tenants.models import Tenant

from .models import Plan, Subscription, SubscriptionPayment

TZ = ZoneInfo("America/Sao_Paulo")


def _month_start(day: date, back: int = 0) -> date:
    index = day.year * 12 + day.month - 1 - back
    return date(index // 12, index % 12 + 1, 1)


def _start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=TZ)


def effective_status(tenant: Tenant, sub: Subscription | None) -> str:
    """Situação para o painel: bloqueado pelo dono, isento, ou a da assinatura."""
    if tenant.status == Tenant.Status.SUSPENDED:
        return "SUSPENDED"
    if sub is None:
        return Subscription.Status.EXEMPT
    return sub.status


# ---------------------------------------------------------------- visão geral


def overview(now: datetime | None = None) -> dict[str, Any]:
    now = now or timezone.now()
    today = now.astimezone(TZ).date()
    tenants = list(Tenant.objects.all())
    subs = {s.tenant_id: s for s in Subscription.objects.select_related("plan")}
    counts: dict[str, int] = {}
    mrr = Decimal("0")
    for t in tenants:
        status = effective_status(t, subs.get(t.id))
        counts[status] = counts.get(status, 0) + 1
        sub = subs.get(t.id)
        if status == Subscription.Status.ACTIVE and sub and sub.plan:
            mrr += sub.plan.price

    expiring = [
        _office_row(t, subs[t.id])
        for t in tenants
        if (s := subs.get(t.id))
        and s.status == Subscription.Status.TRIAL
        and s.trial_ends_at
        and now <= s.trial_ends_at <= now + timedelta(days=7)
        and t.status == Tenant.Status.ACTIVE
    ]
    attention = [
        _office_row(t, subs[t.id])
        for t in tenants
        if (s := subs.get(t.id))
        and t.status == Tenant.Status.ACTIVE
        and (
            s.status in (Subscription.Status.PAST_DUE, Subscription.Status.PENDING)
            or s.is_blocked(now)
        )
        and s.status != Subscription.Status.EXEMPT
    ]

    revenue = []
    for back in range(5, -1, -1):
        first = _month_start(today, back)
        nxt = _month_start(today, back - 1)
        total = SubscriptionPayment.objects.filter(
            status=SubscriptionPayment.Status.PAID,
            paid_at__gte=_start(first),
            paid_at__lt=_start(nxt),
        ).aggregate(v=Sum("amount"))["v"] or Decimal("0")
        revenue.append({"month": first, "total": total})

    signups = []
    week_start = today - timedelta(days=today.weekday())
    for back in range(7, -1, -1):
        start = week_start - timedelta(weeks=back)
        n = (
            Subscription.objects.filter(
                created_at__gte=_start(start), created_at__lt=_start(start + timedelta(weeks=1))
            )
            .exclude(status=Subscription.Status.EXEMPT)
            .count()
        )
        signups.append({"week": start, "count": n})

    # Conversão: dos testes que já terminaram (últimos 90 dias), quantos viraram pagantes.
    ended = Subscription.objects.filter(
        trial_ends_at__lt=now, trial_ends_at__gte=now - timedelta(days=90)
    ).exclude(status=Subscription.Status.EXEMPT)
    converted = ended.filter(payments__status=SubscriptionPayment.Status.PAID).distinct().count()
    total_ended = ended.count()

    return {
        "mrr": mrr,
        "offices": len(tenants),
        "by_status": counts,
        "conversion": round(100 * converted / total_ended, 1) if total_ended else None,
        "trials_ending": sorted(expiring, key=lambda r: r["trial_ends_at"]),
        "attention": attention,
        "revenue_by_month": revenue,
        "signups_by_week": signups,
    }


# ---------------------------------------------------------------- escritórios


def _owner(tenant_id: uuid.UUID) -> User | None:
    m = (
        Membership.objects.filter(tenant_id=tenant_id, role=Membership.Role.OWNER, is_active=True)
        .select_related("user")
        .order_by("created_at")
        .first()
    )
    return m.user if m else None


def _office_row(tenant: Tenant, sub: Subscription | None) -> dict[str, Any]:
    owner = _owner(tenant.id)
    last = (
        sub.payments.filter(status=SubscriptionPayment.Status.PAID).order_by("-paid_at").first()
        if sub
        else None
    )
    return {
        "id": tenant.id,
        "name": tenant.name,
        "created_at": tenant.created_at,
        "status": effective_status(tenant, sub),
        "plan_code": sub.plan.code if sub and sub.plan else "",
        "plan_name": sub.plan.name if sub and sub.plan else "",
        "price": sub.plan.price if sub and sub.plan else None,
        "trial_ends_at": sub.trial_ends_at if sub else None,
        "paid_until": sub.paid_until if sub else None,
        "access_until": sub.access_until() if sub else None,
        "blocked": bool(sub and sub.is_blocked()) or tenant.status == Tenant.Status.SUSPENDED,
        "owner_name": (owner.full_name if owner else "") or "",
        "owner_email": owner.email if owner else "",
        "last_payment_at": last.paid_at if last else None,
        "checkout_url": sub.mp_init_point
        if sub and sub.status == Subscription.Status.PENDING
        else "",
    }


def usage(tenant_id: uuid.UUID, since: datetime) -> dict[str, int]:
    """Só contagens (nada de conteúdo). Precisa de transação aberta (request)."""
    from apps.clientes.models import Client
    from apps.ia.models import AiGeneration
    from apps.whatsapp.models import Message

    members = Membership.objects.filter(tenant_id=tenant_id, is_active=True).count()
    with tenant_context(tenant_id):
        messages = Message.objects.filter(created_at__gte=since).aggregate(
            inbound=Count("id", filter=Q(direction=Message.Direction.INBOUND)),
            outbound=Count("id", filter=Q(direction=Message.Direction.OUTBOUND)),
        )
        return {
            "members": members,
            "clients": Client.objects.count(),
            "messages_in": messages["inbound"],
            "messages_out": messages["outbound"],
            "ai_calls": AiGeneration.objects.filter(created_at__gte=since).count(),
        }


def offices(q: str = "", status: str = "") -> list[dict[str, Any]]:
    subs = {s.tenant_id: s for s in Subscription.objects.select_related("plan")}
    qs = Tenant.objects.order_by("-created_at")
    if q.strip():
        owners = Membership.objects.filter(
            role=Membership.Role.OWNER, user__email__icontains=q.strip()
        ).values("tenant_id")
        qs = qs.filter(Q(name__icontains=q.strip()) | Q(id__in=owners))
    month = _start(_month_start(timezone.now().astimezone(TZ).date()))
    rows = []
    for tenant in qs[:300]:
        row = _office_row(tenant, subs.get(tenant.id))
        if status and row["status"] != status:
            continue
        row["usage"] = usage(tenant.id, month)
        rows.append(row)
    return rows


def office(tenant_id: uuid.UUID) -> dict[str, Any]:
    tenant = Tenant.objects.filter(pk=tenant_id).first()
    if tenant is None:
        raise ApiError("Escritório não encontrado.", code="not_found", status_code=404)
    sub = Subscription.objects.select_related("plan").filter(tenant=tenant).first()
    row = _office_row(tenant, sub)
    row["usage"] = usage(tenant.id, _start(_month_start(timezone.now().astimezone(TZ).date())))
    row["payments"] = (
        list(_payments(SubscriptionPayment.objects.filter(subscription=sub))) if sub else []
    )
    with tenant_context(tenant.id):
        row["history"] = [
            {
                "at": e.created_at,
                "action": e.action,
                "by": (e.actor_user.full_name or e.actor_user.email) if e.actor_user else "",
                "data": e.data,
            }
            for e in audit.history(tenant).filter(action__startswith="platform.")[:30]
        ]
    return row


def _payments(qs: Any) -> Any:
    for p in qs.select_related("subscription__tenant", "created_by").order_by("-paid_at")[:200]:
        yield {
            "id": p.pk,
            "office_id": p.subscription.tenant_id,
            "office_name": p.subscription.tenant.name,
            "source": p.source,
            "status": p.status,
            "amount": p.amount,
            "paid_at": p.paid_at,
            "note": p.note,
            "created_by": (p.created_by.full_name or p.created_by.email) if p.created_by else "",
        }


def payments() -> list[dict[str, Any]]:
    return list(_payments(SubscriptionPayment.objects.all()))


# ---------------------------------------------------------------- ações


@dataclass
class _Target:
    tenant: Tenant
    sub: Subscription


def _target(tenant_id: uuid.UUID, *, create: bool = True) -> _Target:
    tenant = Tenant.objects.select_for_update().filter(pk=tenant_id).first()
    if tenant is None:
        raise ApiError("Escritório não encontrado.", code="not_found", status_code=404)
    sub = Subscription.objects.select_for_update().filter(tenant=tenant).first()
    if sub is None:
        if not create:
            raise ApiError("Escritório sem assinatura.", code="no_subscription")
        # Sem linha = isento (criado manualmente). Passa a ter registro explícito.
        sub = Subscription.objects.create(tenant=tenant, status=Subscription.Status.EXEMPT)
    return _Target(tenant, sub)


def _log(tenant: Tenant, action: str, user: User, **data: Any) -> None:
    with tenant_context(tenant.id):
        audit.record(
            f"platform.{action}",
            tenant,
            actor_type=audit.Actor.USER,
            actor_user=user,
            data={k: str(v) for k, v in data.items()},
        )


def extend_trial(tenant_id: uuid.UUID, *, days: int, user: User) -> None:
    if not 1 <= days <= 90:
        raise ApiError("Entre 1 e 90 dias.", code="invalid_days")
    t = _target(tenant_id)
    if t.sub.status == Subscription.Status.EXEMPT:
        raise ApiError("Escritório isento: não precisa de teste.", code="exempt")
    base = max(t.sub.trial_ends_at or timezone.now(), timezone.now())
    t.sub.trial_ends_at = base + timedelta(days=days)
    if t.sub.status not in (Subscription.Status.ACTIVE, Subscription.Status.PENDING):
        t.sub.status = Subscription.Status.TRIAL
    t.sub.save()
    _log(t.tenant, "trial_extended", user, days=days, until=t.sub.trial_ends_at.date())


def set_exempt(tenant_id: uuid.UUID, *, exempt: bool, user: User) -> None:
    t = _target(tenant_id)
    if exempt:
        t.sub.status = Subscription.Status.EXEMPT
    elif t.sub.status == Subscription.Status.EXEMPT:
        from .services import default_plan

        t.sub.plan = t.sub.plan or default_plan()  # isento costuma não ter plano
        now = timezone.now()
        if t.sub.paid_until and t.sub.paid_until > now:
            t.sub.status = Subscription.Status.ACTIVE
        else:
            # Volta a pagar: 7 dias para assinar antes de bloquear.
            t.sub.status = Subscription.Status.TRIAL
            t.sub.trial_ends_at = now + timedelta(days=7)
    t.sub.save()
    _log(t.tenant, "exempt_on" if exempt else "exempt_off", user)


def set_suspended(tenant_id: uuid.UUID, *, suspended: bool, user: User) -> None:
    t = _target(tenant_id)
    if suspended and Membership.objects.filter(tenant=t.tenant, user=user, is_active=True).exists():
        raise ApiError(
            "Você faz parte deste escritório: bloqueá-lo tiraria o seu próprio acesso.",
            code="own_office",
            status_code=http_status.HTTP_409_CONFLICT,
        )
    t.tenant.status = Tenant.Status.SUSPENDED if suspended else Tenant.Status.ACTIVE
    t.tenant.save(update_fields=["status"])
    _log(t.tenant, "suspended" if suspended else "unsuspended", user)


def change_plan(tenant_id: uuid.UUID, *, plan_code: str, user: User) -> None:
    plan = Plan.objects.filter(code=plan_code).first()
    if plan is None:
        raise ApiError("Plano não encontrado.", code="not_found", status_code=404)
    t = _target(tenant_id)
    previous = t.sub.plan.code if t.sub.plan else ""
    t.sub.plan = plan
    t.sub.save(update_fields=["plan", "updated_at"])
    _log(t.tenant, "plan_changed", user, de=previous or "-", para=plan.code)


def add_months(value: datetime, months: int) -> datetime:
    from apps.financeiro.services import add_months as add_months_date

    local = value.astimezone(TZ)
    return datetime.combine(add_months_date(local.date(), months), local.timetz())


def manual_payment(
    tenant_id: uuid.UUID, *, amount: Decimal, months: int, note: str, user: User
) -> None:
    """Pagamento recebido fora do Mercado Pago (Pix direto, transferência): libera o acesso."""
    if not 1 <= months <= 24:
        raise ApiError("Entre 1 e 24 meses.", code="invalid_months")
    t = _target(tenant_id)
    now = timezone.now()
    SubscriptionPayment.objects.create(
        subscription=t.sub,
        source=SubscriptionPayment.Source.MANUAL,
        status=SubscriptionPayment.Status.PAID,
        amount=amount,
        paid_at=now,
        note=note.strip()[:255],
        created_by=user,
    )
    t.sub.paid_until = add_months(max(t.sub.paid_until or now, now), months)
    if t.sub.status != Subscription.Status.EXEMPT:
        t.sub.status = Subscription.Status.ACTIVE
    t.sub.save()
    _log(t.tenant, "manual_payment", user, valor=amount, meses=months, ate=t.sub.paid_until.date())


def payer_email(tenant_id: uuid.UUID) -> str:
    sub = Subscription.objects.filter(tenant_id=tenant_id).first()
    owner = _owner(tenant_id)
    return (sub.payer_email if sub and sub.payer_email else "") or (owner.email if owner else "")


def office_checkout(tenant_id: uuid.UUID) -> dict[str, str]:
    """Link pendente que já existe (se houver) e o e-mail para criar um novo."""
    sub = Subscription.objects.filter(tenant_id=tenant_id).first()
    if sub is None or sub.status == Subscription.Status.EXEMPT:
        raise ApiError("Escritório isento: não tem cobrança.", code="exempt")
    pending = sub.mp_init_point if sub.status == Subscription.Status.PENDING else ""
    return {"checkout_url": pending, "payer_email": payer_email(tenant_id)}

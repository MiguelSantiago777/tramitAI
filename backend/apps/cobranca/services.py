"""Assinatura do TramitAI: teste grátis, assinatura no Mercado Pago e bloqueio por falta de
pagamento. Chamadas ao MP sempre fora de transação."""

import logging
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import status as http_status

from apps.accounts.models import Membership, User
from apps.core.exceptions import ApiError
from apps.core.mercadopago import MercadoPagoError, get_mercadopago, public_url
from apps.tenants.models import Tenant
from apps.tenants.services import CreatedTenant, create_tenant

from .models import Plan, Subscription

logger = logging.getLogger(__name__)


def default_plan() -> Plan | None:
    return Plan.objects.filter(is_active=True).order_by("sort", "price").first()


def subscription_for(tenant_id: uuid.UUID) -> Subscription | None:
    return Subscription.objects.select_related("plan").filter(tenant_id=tenant_id).first()


def is_blocked(tenant_id: uuid.UUID) -> bool:
    """Sem linha de assinatura = escritório criado manualmente (isento)."""
    sub = (
        Subscription.objects.filter(tenant_id=tenant_id)
        .only("status", "trial_ends_at", "paid_until")
        .first()
    )
    return bool(sub and sub.is_blocked())


# ---------------------------------------------------------------- cadastro


def _unique_slug(name: str) -> str:
    base = slugify(name)[:50] or "escritorio"
    slug, n = base, 1
    while Tenant.objects.filter(slug=slug).exists():
        n += 1
        slug = f"{base}-{n}"
    return slug


def signup(*, office_name: str, full_name: str, email: str, password: str) -> CreatedTenant:
    """Cadastro público: escritório novo + titular + teste grátis.

    E-mail já cadastrado é recusado (senão alguém criaria escritório "em nome" de outra pessoa
    e ficaria vinculado à conta dela).
    """
    if not settings.SIGNUP_ENABLED:
        raise ApiError("Cadastro fechado no momento.", code="signup_disabled", status_code=403)
    if User.objects.filter(email__iexact=email).exists():
        raise ApiError(
            "Já existe uma conta com este e-mail. Entre com ela ou use outro e-mail.",
            code="email_taken",
            status_code=http_status.HTTP_409_CONFLICT,
        )
    try:
        with transaction.atomic():
            created = create_tenant(
                name=office_name.strip(),
                owner_email=email,
                owner_password=password,
                owner_full_name=full_name.strip(),
                slug=_unique_slug(office_name),
            )
            Subscription.objects.create(
                tenant=created.tenant,
                plan=default_plan(),
                status=Subscription.Status.TRIAL,
                trial_ends_at=timezone.now() + timedelta(days=settings.TRIAL_DAYS),
                payer_email=email,
            )
    except IntegrityError as exc:
        raise ApiError("Não foi possível criar agora. Tente de novo.", code="conflict") from exc
    return created


# ---------------------------------------------------------------- assinatura no MP


@dataclass(frozen=True)
class BillingStatus:
    status: str
    status_label: str
    plan_name: str
    price: str
    trial_ends_at: datetime | None
    paid_until: datetime | None
    access_until: datetime | None
    days_left: int | None
    blocked: bool
    payer_email: str
    checkout_url: str
    can_manage: bool
    exempt: bool


def billing_status(tenant_id: uuid.UUID, membership: Membership) -> BillingStatus:
    sub = subscription_for(tenant_id)
    can_manage = membership.role == Membership.Role.OWNER
    if sub is None or sub.status == Subscription.Status.EXEMPT:
        plan = sub.plan if sub else None
        return BillingStatus(
            status=Subscription.Status.EXEMPT,
            status_label=Subscription.Status.EXEMPT.label,
            plan_name=plan.name if plan else "",
            price=str(plan.price) if plan else "",
            trial_ends_at=None,
            paid_until=None,
            access_until=None,
            days_left=None,
            blocked=False,
            payer_email="",
            checkout_url="",
            can_manage=can_manage,
            exempt=True,
        )
    plan = sub.plan or default_plan()
    until = sub.access_until()
    # Arredonda para cima: no 1º dia do teste de 14 dias aparece "14", não "13".
    days_left = (
        max(math.ceil((until - timezone.now()).total_seconds() / 86400), 0) if until else None
    )
    return BillingStatus(
        status=sub.status,
        status_label=sub.get_status_display(),
        plan_name=plan.name if plan else "",
        price=str(plan.price) if plan else "",
        trial_ends_at=sub.trial_ends_at,
        paid_until=sub.paid_until,
        access_until=until,
        days_left=days_left,
        blocked=sub.is_blocked(),
        payer_email=sub.payer_email,
        checkout_url=sub.mp_init_point if sub.status == Subscription.Status.PENDING else "",
        can_manage=can_manage,
        exempt=False,
    )


def _platform_token() -> str:
    token = settings.MERCADOPAGO_PLATFORM_TOKEN
    if not token:
        raise ApiError(
            "Pagamento da assinatura ainda não configurado. Fale com o suporte do TramitAI.",
            code="billing_not_configured",
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return token


def start_checkout(tenant_id: uuid.UUID, *, payer_email: str) -> str:
    """Cria a assinatura recorrente no MP e devolve o link de pagamento (checkout do MP)."""
    token = _platform_token()
    with transaction.atomic():
        sub = (
            Subscription.objects.select_for_update(of=("self",))
            .select_related("plan", "tenant")
            .filter(tenant_id=tenant_id)
            .first()
        )
        if sub is None or sub.status == Subscription.Status.EXEMPT:
            raise ApiError("Este escritório não precisa de assinatura.", code="exempt")
        if sub.status == Subscription.Status.ACTIVE and sub.mp_preapproval_id:
            raise ApiError("A assinatura já está ativa.", code="already_active")
        plan = sub.plan or default_plan()
        if plan is None:
            raise ApiError("Nenhum plano disponível.", code="no_plan", status_code=503)
        reason = f"TramitAI - {plan.name} - {sub.tenant.name}"
        amount = plan.price
        old_preapproval = sub.mp_preapproval_id if sub.status == Subscription.Status.PENDING else ""

    client = get_mercadopago()
    try:
        if old_preapproval:
            # Checkout antigo não pago (ex.: trocou o e-mail): cancela para não ficarem dois.
            try:
                client.cancel_subscription(token, old_preapproval)
            except MercadoPagoError:
                logger.info("cobranca: checkout antigo não cancelado (segue)")
        created = client.create_subscription(
            token,
            reason=reason,
            amount=amount,
            payer_email=payer_email,
            external_reference=str(tenant_id),
            back_url=f"{settings.FRONTEND_URL.rstrip('/')}/assinatura?retorno=1",
            notification_url=public_url("/api/webhooks/mercadopago-assinatura/"),
        )
    except MercadoPagoError as exc:
        logger.warning("cobranca: falha ao criar assinatura (%s)", exc.code)
        raise ApiError(
            "O Mercado Pago não aceitou agora. Confira o e-mail (precisa ser o da sua conta no "
            "Mercado Pago) e tente de novo.",
            code="mercadopago_error",
            status_code=http_status.HTTP_502_BAD_GATEWAY,
        ) from exc

    with transaction.atomic():
        sub = Subscription.objects.select_for_update().get(tenant_id=tenant_id)
        sub.plan = sub.plan or plan
        sub.mp_preapproval_id = created.preapproval_id
        sub.mp_status = created.status
        sub.mp_init_point = created.init_point
        sub.payer_email = payer_email
        if sub.status != Subscription.Status.ACTIVE:
            sub.status = Subscription.Status.PENDING
        sub.save()
    return created.init_point


def sync_subscription(preapproval_id: str) -> str:
    """Consulta a assinatura no MP e atualiza o acesso. Idempotente; serve para aviso e beat."""
    token = _platform_token()
    remote = get_mercadopago().get_subscription(token, preapproval_id)
    try:
        tenant_id = uuid.UUID(remote.external_reference)
    except ValueError:
        return "foreign"
    with transaction.atomic():
        sub = Subscription.objects.select_for_update().filter(tenant_id=tenant_id).first()
        if sub is None or sub.status == Subscription.Status.EXEMPT:
            return "ignored"
        if sub.mp_preapproval_id and sub.mp_preapproval_id != preapproval_id:
            if remote.status != "authorized":
                return "stale"  # checkout antigo que ninguém pagou
            sub.mp_preapproval_id = preapproval_id
        sub.mp_status = remote.status
        if remote.status == "authorized":
            sub.status = Subscription.Status.ACTIVE
            # Pago até a próxima cobrança; sem a data, um mês a partir de agora.
            next_charge = remote.next_payment_date or (timezone.now() + timedelta(days=31))
            if not sub.paid_until or next_charge > sub.paid_until:
                sub.paid_until = next_charge
        elif remote.status == "paused":
            sub.status = Subscription.Status.PAST_DUE
        elif remote.status == "cancelled":
            sub.status = Subscription.Status.CANCELLED  # usa até o fim do período pago
        sub.save()
        return sub.status


def sync_from_authorized_payment(payment_id: str) -> str:
    preapproval_id = get_mercadopago().authorized_payment_subscription(
        _platform_token(), payment_id
    )
    return sync_subscription(preapproval_id) if preapproval_id else "unknown"


def cancel(tenant_id: uuid.UUID) -> None:
    token = _platform_token()
    sub = subscription_for(tenant_id)
    if sub is None or not sub.mp_preapproval_id:
        raise ApiError("Não há assinatura para cancelar.", code="no_subscription")
    try:
        get_mercadopago().cancel_subscription(token, sub.mp_preapproval_id)
    except MercadoPagoError as exc:
        raise ApiError(
            "O Mercado Pago não respondeu. Tente de novo.",
            code="mercadopago_error",
            status_code=http_status.HTTP_502_BAD_GATEWAY,
        ) from exc
    with transaction.atomic():
        Subscription.objects.filter(pk=sub.pk).update(
            status=Subscription.Status.CANCELLED, mp_status="cancelled", updated_at=timezone.now()
        )


def refresh_all() -> int:
    """Beat diário: confere no MP as assinaturas com checkout (cobre aviso perdido)."""
    if not settings.MERCADOPAGO_PLATFORM_TOKEN:
        return 0
    ids = list(
        Subscription.objects.exclude(mp_preapproval_id="")
        .exclude(status=Subscription.Status.EXEMPT)
        .values_list("mp_preapproval_id", flat=True)
    )
    done = 0
    for preapproval_id in ids:
        try:
            sync_subscription(preapproval_id)
            done += 1
        except MercadoPagoError as exc:
            logger.warning("cobranca: assinatura não conferida (%s)", exc.code)
    return done

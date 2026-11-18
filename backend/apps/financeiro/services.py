"""Regras do financeiro: parcelamento, baixa, cobrança pelo Mercado Pago e lembretes.

Cobrança no Mercado Pago em três fases (regra do projeto: nada de HTTP com transação aberta):
prepare (transação curta) → chamada ao MP (fora) → store (transação curta).
"""

import calendar
import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_DOWN, Decimal
from typing import Any
from zoneinfo import ZoneInfo

from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import status as http_status

from apps.accounts.models import User
from apps.clientes.models import Client
from apps.core import audit
from apps.core.crypto import decrypt_secret, encrypt_secret
from apps.core.exceptions import ApiError
from apps.core.mercadopago import (
    MercadoPagoError,
    Payer,
    get_mercadopago,
    public_url,
)
from apps.core.tenancy import tenant_atomic
from apps.processos.models import LegalCase
from apps.tenants.models import Tenant

from .models import ZERO, FeeAgreement, Installment, MercadoPagoAccount, PaymentWebhookRoute

logger = logging.getLogger(__name__)
TZ = ZoneInfo("America/Sao_Paulo")
MAX_INSTALLMENTS = 120
# Pix vale até o fim do dia do vencimento (ou 3 dias, se já venceu); link, 30 dias.
LINK_DAYS = 30

PAYMENT_TYPE_TO_METHOD = {
    "bank_transfer": Installment.Method.PIX,
    "ticket": Installment.Method.BOLETO,
    "credit_card": Installment.Method.CARTAO,
    "debit_card": Installment.Method.CARTAO,
    "prepaid_card": Installment.Method.CARTAO,
    "account_money": Installment.Method.TRANSFERENCIA,
}


# ---------------------------------------------------------------- parcelamento


def add_months(start: date, months: int) -> date:
    """Mesmo dia nos meses seguintes; dia 31 vira o último dia do mês quando não existe."""
    month_index = start.month - 1 + months
    year, month = start.year + month_index // 12, month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def plan_installments(
    total: Decimal, count: int, first_due: date, *, entry: Decimal | None = None
) -> list[tuple[int, date, Decimal]]:
    """Divide o total em parcelas mensais. Centavos que sobram vão para a primeira parcela.

    Com entrada: parcela 1 = entrada (no primeiro vencimento) e o resto em `count` parcelas a
    partir do mês seguinte.
    """
    if total <= 0:
        raise ApiError("O valor total precisa ser maior que zero.", code="invalid_amount")
    if not 1 <= count <= MAX_INSTALLMENTS:
        raise ApiError(
            f"Número de parcelas entre 1 e {MAX_INSTALLMENTS}.", code="invalid_installments"
        )
    plan: list[tuple[int, date, Decimal]] = []
    remaining, start_offset = total, 0
    if entry:
        if not ZERO < entry < total:
            raise ApiError(
                "A entrada precisa ser maior que zero e menor que o total.", code="invalid_entry"
            )
        plan.append((1, first_due, entry))
        remaining, start_offset = total - entry, 1
    base = (remaining / count).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    leftover = remaining - base * count
    for i in range(count):
        amount = base + (leftover if i == 0 else ZERO)
        plan.append((len(plan) + 1, add_months(first_due, i + start_offset), amount))
    return plan


def create_agreement(
    *,
    user: User,
    client: Client,
    title: str,
    total_amount: Decimal,
    installments: int,
    first_due: date,
    kind: str = FeeAgreement.Kind.CONTRATUAL,
    legal_case: LegalCase | None = None,
    entry_amount: Decimal | None = None,
    notes: str = "",
) -> FeeAgreement:
    plan = plan_installments(total_amount, installments, first_due, entry=entry_amount)
    agreement = FeeAgreement.objects.create(
        client=client,
        legal_case=legal_case,
        title=title.strip() or f"Honorários de {client.name}",
        kind=kind,
        total_amount=total_amount,
        notes=notes.strip(),
        created_by=user,
    )
    Installment.objects.bulk_create(
        [
            Installment(
                tenant_id=agreement.tenant_id, agreement=agreement, number=n, due_date=d, amount=a
            )
            for n, d, a in plan
        ]
    )
    audit.record(
        "fees.agreement_created",
        agreement,
        actor_type=audit.Actor.USER,
        actor_user=user,
        data={"installments": len(plan), "total": str(total_amount)},
    )
    return agreement


def _refresh_agreement_status(agreement: FeeAgreement) -> None:
    if agreement.status == FeeAgreement.Status.CANCELLED:
        return
    open_count = agreement.installments.filter(status=Installment.Status.OPEN).count()
    new_status = FeeAgreement.Status.ACTIVE if open_count else FeeAgreement.Status.FINISHED
    if new_status != agreement.status:
        agreement.status = new_status
        agreement.save(update_fields=["status", "updated_at"])


def _lock(installment_id: Any) -> Installment:
    installment = (
        Installment.objects.select_for_update(of=("self",))
        .select_related("agreement__client")
        .filter(pk=installment_id)
        .first()
    )
    if installment is None:
        raise ApiError("Parcela não encontrada.", code="not_found", status_code=404)
    return installment


def settle(
    installment: Installment,
    *,
    user: User | None,
    method: str,
    paid_amount: Decimal | None = None,
    paid_at: datetime | None = None,
    note: str = "",
    mp_payment_id: str = "",
) -> Installment:
    """Dá baixa (manual pela equipe ou automática pelo Mercado Pago)."""
    installment = _lock(installment.pk)
    if installment.status != Installment.Status.OPEN:
        raise ApiError(
            "Esta parcela não está em aberto.",
            code="installment_not_open",
            status_code=http_status.HTTP_409_CONFLICT,
        )
    installment.status = Installment.Status.PAID
    installment.paid_at = paid_at or timezone.now()
    installment.paid_amount = paid_amount if paid_amount is not None else installment.amount
    installment.method = method
    installment.paid_note = note.strip()[:255]
    installment.settled_by = user
    if mp_payment_id:
        installment.mp_payment_id = mp_payment_id
    installment.save()
    _refresh_agreement_status(installment.agreement)
    audit.record(
        "fees.installment_paid",
        installment,
        actor_type=audit.Actor.USER if user else audit.Actor.SYSTEM,
        actor_user=user,
        data={
            "method": method,
            "amount": str(installment.paid_amount),
            "via": "mercadopago" if mp_payment_id else "manual",
        },
    )
    return installment


def reopen(installment: Installment, *, user: User) -> Installment:
    """Desfaz uma baixa manual feita por engano."""
    installment = _lock(installment.pk)
    if installment.status == Installment.Status.OPEN:
        return installment
    if (
        installment.status == Installment.Status.PAID
        and installment.mp_payment_id
        and (installment.settled_by_id is None)
    ):
        raise ApiError(
            "Pagamento confirmado pelo Mercado Pago não pode ser reaberto aqui. "
            "Se houve estorno, faça pelo Mercado Pago.",
            code="paid_by_mercadopago",
        )
    previous = installment.status
    installment.status = Installment.Status.OPEN
    installment.paid_at = None
    installment.paid_amount = None
    installment.method = ""
    installment.paid_note = ""
    installment.settled_by = None
    installment.save()
    _refresh_agreement_status(installment.agreement)
    audit.record(
        "fees.installment_reopened",
        installment,
        actor_type=audit.Actor.USER,
        actor_user=user,
        data={"previous": previous},
    )
    return installment


def cancel_installment(installment: Installment, *, user: User) -> Installment:
    installment = _lock(installment.pk)
    if installment.status != Installment.Status.OPEN:
        raise ApiError("Só parcela em aberto pode ser cancelada.", code="installment_not_open")
    installment.status = Installment.Status.CANCELLED
    installment.save(update_fields=["status", "updated_at"])
    _refresh_agreement_status(installment.agreement)
    audit.record(
        "fees.installment_cancelled", installment, actor_type=audit.Actor.USER, actor_user=user
    )
    return installment


# ---------------------------------------------------------------- resumo


@dataclass(frozen=True)
class Summary:
    month: date
    received: Decimal
    expected: Decimal
    overdue_total: Decimal
    overdue_count: int
    next_30_days: Decimal
    open_total: Decimal


def summary(month: date) -> Summary:
    first = month.replace(day=1)
    last = add_months(first, 1) - timedelta(days=1)
    today = timezone.localdate()
    open_qs = Installment.objects.filter(status=Installment.Status.OPEN)

    def total(qs: Any, field: str = "amount") -> Decimal:
        return qs.aggregate(v=Sum(field))["v"] or ZERO

    start = datetime.combine(first, time.min, tzinfo=TZ)
    end = datetime.combine(last, time.max, tzinfo=TZ)
    overdue = open_qs.filter(due_date__lt=today).aggregate(v=Sum("amount"), n=Count("id"))
    return Summary(
        month=first,
        received=total(
            Installment.objects.filter(
                status=Installment.Status.PAID, paid_at__gte=start, paid_at__lte=end
            ),
            "paid_amount",
        ),
        expected=total(
            Installment.objects.filter(due_date__gte=first, due_date__lte=last).exclude(
                status=Installment.Status.CANCELLED
            )
        ),
        overdue_total=overdue["v"] or ZERO,
        overdue_count=overdue["n"] or 0,
        next_30_days=total(
            open_qs.filter(due_date__gte=today, due_date__lte=today + timedelta(days=30))
        ),
        open_total=total(open_qs),
    )


# ---------------------------------------------------------------- Mercado Pago (conta)


def account() -> MercadoPagoAccount | None:
    return MercadoPagoAccount.objects.first()


def webhook_url(tenant_id: uuid.UUID) -> str:
    route, _ = PaymentWebhookRoute.objects.get_or_create(tenant_id=tenant_id)
    return public_url(f"/api/webhooks/mercadopago/{route.token}/")


def connect_account(tenant_id: uuid.UUID, *, token: str, user: User) -> MercadoPagoAccount:
    """Valida o token no MP (fora de transação) e guarda cifrado."""
    token = token.strip()
    if not token.startswith(("APP_USR-", "TEST-")):
        raise ApiError(
            "Cole o Access Token de produção do Mercado Pago (começa com APP_USR-).",
            code="invalid_token_format",
        )
    try:
        mp_account = get_mercadopago().whoami(token)
    except MercadoPagoError as exc:
        raise _mp_api_error(exc) from exc
    with tenant_atomic(tenant_id):
        current = account()
        if current is None:
            current = MercadoPagoAccount(connected_by=user)
        current.access_token_encrypted = encrypt_secret(token)
        current.mp_user_id = mp_account.user_id
        current.nickname = mp_account.nickname
        current.connected_by = user
        current.save()
        PaymentWebhookRoute.objects.get_or_create(tenant_id=tenant_id)
        audit.record(
            "fees.mercadopago_connected",
            current,
            actor_type=audit.Actor.USER,
            actor_user=user,
            data={"mp_user_id": mp_account.user_id},
        )
    return current


def disconnect_account(*, user: User) -> None:
    current = account()
    if current is not None:
        audit.record(
            "fees.mercadopago_disconnected", current, actor_type=audit.Actor.USER, actor_user=user
        )
        current.delete()


def _token() -> str:
    current = account()
    if current is None:
        raise ApiError(
            "Conecte a conta do Mercado Pago do escritório em Configurações → Financeiro.",
            code="mercadopago_not_connected",
        )
    return decrypt_secret(current.access_token_encrypted)


def _mp_api_error(exc: MercadoPagoError) -> ApiError:
    if exc.code == "invalid_token":
        return ApiError(
            "O Mercado Pago recusou o Access Token. Confira e cole de novo.",
            code="mercadopago_invalid_token",
        )
    return ApiError(
        "O Mercado Pago não respondeu agora. Tente de novo em alguns minutos.",
        code="mercadopago_unavailable",
        status_code=http_status.HTTP_502_BAD_GATEWAY,
    )


# ---------------------------------------------------------------- cobrança


def _payer(client: Client) -> Payer:
    parts = (client.name or "").split()
    email = client.email or f"cliente-{client.pk.hex[:12]}@sem-email.tramitai.pro"
    return Payer(
        email=email,
        first_name=parts[0] if parts else "",
        last_name=" ".join(parts[1:]),
        cpf_cnpj=client.cpf_cnpj,
    )


def _charge_expiry(installment: Installment, kind: str) -> datetime:
    now = timezone.now()
    if kind == Installment.ChargeKind.LINK:
        return now + timedelta(days=LINK_DAYS)
    end_of_due = datetime.combine(installment.due_date, time(23, 59, 59), tzinfo=TZ)
    return end_of_due if end_of_due > now + timedelta(hours=1) else now + timedelta(days=3)


def create_charge(
    tenant_id: uuid.UUID, installment_id: uuid.UUID, *, kind: str, user: User
) -> Installment:
    """Gera (ou reaproveita) a cobrança da parcela no Mercado Pago."""
    with tenant_atomic(tenant_id):
        installment = _lock(installment_id)
        if installment.status != Installment.Status.OPEN:
            raise ApiError("Esta parcela não está em aberto.", code="installment_not_open")
        if installment.has_active_charge and installment.charge_kind == kind:
            return installment
        token = _token()
        agreement = installment.agreement
        payer = _payer(agreement.client)
        expires_at = _charge_expiry(installment, kind)
        amount, number = installment.amount, installment.number
        title = f"{agreement.title} - parcela {number}"
        notify = webhook_url(tenant_id)
        reference = str(installment.pk)
        # Mesma chave = MP devolve a mesma cobrança se repetirmos depois de um timeout.
        idempotency = f"{installment.pk}-{kind}-{expires_at:%Y%m%d}-{amount}"

    client = get_mercadopago()
    try:
        if kind == Installment.ChargeKind.PIX:
            pix = client.create_pix(
                token,
                amount=amount,
                description=title,
                payer=payer,
                external_reference=reference,
                notification_url=notify,
                expires_at=expires_at,
                idempotency_key=idempotency,
            )
            fields: dict[str, Any] = {
                "mp_payment_id": pix.payment_id,
                "mp_preference_id": "",
                "pix_code": pix.qr_code,
                "pix_qr_base64": pix.qr_code_base64,
                "payment_url": pix.ticket_url,
            }
        else:
            link = client.create_link(
                token,
                title=title,
                amount=amount,
                payer=payer,
                external_reference=reference,
                notification_url=notify,
                expires_at=expires_at,
            )
            fields = {
                "mp_payment_id": "",
                "mp_preference_id": link.preference_id,
                "pix_code": "",
                "pix_qr_base64": "",
                "payment_url": link.url,
            }
    except MercadoPagoError as exc:
        raise _mp_api_error(exc) from exc

    with tenant_atomic(tenant_id):
        installment = _lock(installment_id)
        if installment.status != Installment.Status.OPEN:
            return installment  # pago enquanto gerávamos
        for name, value in fields.items():
            setattr(installment, name, value)
        installment.charge_kind = kind
        installment.charge_expires_at = expires_at
        installment.save()
        audit.record(
            "fees.charge_created",
            installment,
            actor_type=audit.Actor.USER,
            actor_user=user,
            data={"kind": kind, "mp_payment_id": fields["mp_payment_id"]},
        )
        return installment


def charge_message(installment: Installment) -> str:
    """Texto da cobrança para o WhatsApp (o advogado revisa antes de enviar)."""
    agreement = installment.agreement
    first_name = (agreement.client.name or "").split(" ")[0]
    amount = f"R$ {installment.amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    due = installment.due_date.strftime("%d/%m/%Y")
    lines = [
        f"Olá{', ' + first_name if first_name else ''}! Segue a parcela {installment.number} "
        f"de {agreement.title}: {amount}, vencimento {due}.",
    ]
    if installment.has_active_charge and installment.pix_code:
        lines += ["", "Pix copia e cola:", installment.pix_code]
    if installment.has_active_charge and installment.payment_url and not installment.pix_code:
        lines += ["", f"Link para pagar (Pix, boleto ou cartão): {installment.payment_url}"]
    lines += ["", "Qualquer dúvida, é só responder por aqui."]
    return "\n".join(lines)


def send_charge(installment: Installment, *, user: User) -> Any:
    """Envia a cobrança agora pelo WhatsApp (ação humana: quem clica aprova)."""
    from apps.whatsapp import services as whatsapp

    installment = _lock(installment.pk)
    if installment.status != Installment.Status.OPEN:
        raise ApiError("Esta parcela não está em aberto.", code="installment_not_open")
    conversation = whatsapp.conversation_for_client(installment.agreement.client)
    if conversation is None:
        raise ApiError(
            "Cliente sem WhatsApp cadastrado (ou escritório sem WhatsApp conectado).",
            code="no_whatsapp",
        )
    message = whatsapp.queue_text(
        conversation=conversation, body=charge_message(installment), sent_by=user
    )
    installment.last_reminder_on = timezone.localdate()
    installment.save(update_fields=["last_reminder_on", "updated_at"])
    audit.record(
        "fees.charge_sent",
        installment,
        actor_type=audit.Actor.USER,
        actor_user=user,
        data={"message_id": str(message.pk)},
    )
    return message


# ---------------------------------------------------------------- aviso do Mercado Pago


def tenant_for_webhook(token: str) -> uuid.UUID | None:
    route = PaymentWebhookRoute.objects.filter(token=token).first()
    return route.tenant_id if route else None


def sync_payment(tenant_id: uuid.UUID, payment_id: str) -> str:
    """Consulta o pagamento no MP e dá baixa se aprovado. Idempotente."""
    with tenant_atomic(tenant_id):
        try:
            token = _token()
        except ApiError:
            return "not_connected"
    try:
        payment = get_mercadopago().get_payment(token, payment_id)
    except MercadoPagoError as exc:
        if exc.retryable:
            raise
        logger.warning("mercadopago: pagamento não consultado (%s)", exc.code)
        return "not_found"

    try:
        installment_id = uuid.UUID(payment.external_reference)
    except ValueError:
        return "foreign_payment"  # pagamento da conta que não é nosso
    with tenant_atomic(tenant_id):
        installment = Installment.objects.filter(pk=installment_id).first()
        if installment is None:
            return "unknown_installment"
        if payment.status not in ("approved", "authorized"):
            return f"status_{payment.status}"
        if installment.status != Installment.Status.OPEN:
            return "already_settled"
        settle(
            installment,
            user=None,
            method=PAYMENT_TYPE_TO_METHOD.get(payment.payment_type, Installment.Method.OUTRO),
            paid_amount=payment.amount,
            paid_at=payment.date_approved or timezone.now(),
            note="Pago pelo Mercado Pago",
            mp_payment_id=payment.payment_id,
        )
        return "paid"


# ---------------------------------------------------------------- lembretes automáticos


def reminder_text(installment: Installment, overdue: bool) -> str:
    base = charge_message(installment)
    if overdue:
        return base.replace("Segue a parcela", "Lembrete: está em aberto a parcela", 1)
    return base.replace("Segue a parcela", "Lembrete: vence em breve a parcela", 1)


def create_payment_reminders() -> int:
    """Beat diário: parcela vencendo em 3 dias ou vencida há 1/7/15 dias vira rascunho para
    aprovação (não sai sozinho)."""
    from apps.aprovacoes import services as approvals
    from apps.aprovacoes.models import OutboundDraft
    from apps.whatsapp import services as whatsapp

    today = timezone.localdate()
    targets = {today + timedelta(days=3)} | {today - timedelta(days=d) for d in (1, 7, 15)}
    total = 0
    for tenant_id in Tenant.objects.filter(status=Tenant.Status.ACTIVE).values_list(
        "id", flat=True
    ):
        with tenant_atomic(tenant_id):
            due = (
                Installment.objects.select_for_update(of=("self",))
                .select_related("agreement__client")
                .filter(status=Installment.Status.OPEN, due_date__in=targets)
                .filter(Q(last_reminder_on__isnull=True) | Q(last_reminder_on__lt=today))
                .exclude(agreement__status=FeeAgreement.Status.CANCELLED)
            )
            for installment in due:
                installment.last_reminder_on = today
                installment.save(update_fields=["last_reminder_on", "updated_at"])
                conversation = whatsapp.conversation_for_client(installment.agreement.client)
                if conversation is None:
                    continue
                approvals.create_draft(
                    conversation=conversation,
                    origin=OutboundDraft.Origin.PAYMENT_REMINDER,
                    body=reminder_text(installment, installment.due_date < today),
                    actor_type=audit.Actor.SYSTEM,
                    summary=f"Lembrete de pagamento: parcela {installment.number} de "
                    f"{installment.agreement.title}.",
                )
                total += 1
    return total

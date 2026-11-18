"""Financeiro: parcelamento, baixa, Mercado Pago (Pix/link/aviso) e lembretes."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone

from apps.accounts.models import Membership, User
from apps.aprovacoes.models import OutboundDraft
from apps.clientes.models import Client
from apps.core.mercadopago import FakeMercadoPago, MercadoPagoError, Payment, get_mercadopago
from apps.core.tenancy import tenant_atomic, tenant_context
from apps.financeiro import services
from apps.financeiro.models import (
    FeeAgreement,
    Installment,
    MercadoPagoAccount,
    PaymentWebhookRoute,
)

AGREEMENTS = "/api/v1/fee-agreements/"
INSTALLMENTS = "/api/v1/installments/"
MP = "/api/v1/finance/mercadopago/"
TOKEN = "APP_USR-teste"


@pytest.fixture
def mp() -> FakeMercadoPago:
    client = get_mercadopago()
    assert isinstance(client, FakeMercadoPago)
    client.payments.clear()
    client.subscriptions.clear()
    client.created.clear()
    client.cancelled.clear()
    client.fail_next = None
    return client


@pytest.fixture
def ana(tenant_a: Any) -> Client:
    with tenant_context(tenant_a.tenant.id):
        return Client.objects.create(
            name="Ana Souza", phone_e164="+5521998765432", cpf_cnpj="52998224725"
        )


def _create(api_client: Any, client: Client, **extra: Any) -> dict[str, Any]:
    body = {
        "client_id": str(client.pk),
        "title": "Ação trabalhista",
        "total_amount": "1000.00",
        "installments_count": 3,
        "first_due": "2026-01-31",
        **extra,
    }
    response = api_client.post(AGREEMENTS, body, format="json")
    assert response.status_code == 201, response.content
    return response.json()


# ---------------------------------------------------------------- parcelamento


def test_plan_splits_cents_and_clamps_month_end():
    plan = services.plan_installments(Decimal("1000.00"), 3, date(2026, 1, 31))
    assert [p[2] for p in plan] == [Decimal("333.34"), Decimal("333.33"), Decimal("333.33")]
    assert [p[1] for p in plan] == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]
    assert sum(p[2] for p in plan) == Decimal("1000.00")


def test_plan_with_entry():
    plan = services.plan_installments(
        Decimal("1500.00"), 2, date(2026, 5, 10), entry=Decimal("500.00")
    )
    assert [(n, d, a) for n, d, a in plan] == [
        (1, date(2026, 5, 10), Decimal("500.00")),
        (2, date(2026, 6, 10), Decimal("500.00")),
        (3, date(2026, 7, 10), Decimal("500.00")),
    ]


def test_create_agreement_settle_and_finish(tenant_a, ana, login, api_client):
    login(tenant_a.owner.email)
    agreement = _create(api_client, ana)
    assert agreement["client_name"] == "Ana Souza"
    assert [i["amount"] for i in agreement["installments"]] == ["333.34", "333.33", "333.33"]
    assert agreement["open_total"] == "1000.00"

    for inst in agreement["installments"]:
        paid = api_client.post(
            f"{INSTALLMENTS}{inst['id']}/settle/", {"method": "PIX"}, format="json"
        )
        assert paid.status_code == 200
        assert paid.json()["status"] == "PAID"
    again = api_client.post(
        f"{INSTALLMENTS}{agreement['installments'][0]['id']}/settle/",
        {"method": "PIX"},
        format="json",
    )
    assert again.status_code == 409
    detail = api_client.get(f"{AGREEMENTS}{agreement['id']}/").json()
    assert detail["status"] == "FINISHED"
    assert detail["paid_total"] == "1000.00"

    reopened = api_client.post(f"{INSTALLMENTS}{agreement['installments'][0]['id']}/reopen/")
    assert reopened.json()["status"] == "OPEN"
    assert api_client.get(f"{AGREEMENTS}{agreement['id']}/").json()["status"] == "ACTIVE"


def test_filters_and_summary(tenant_a, ana, login, api_client):
    login(tenant_a.owner.email)
    today = timezone.localdate()
    agreement = _create(
        api_client, ana, first_due=(today - timedelta(days=40)).isoformat(), installments_count=3
    )
    overdue = api_client.get(f"{INSTALLMENTS}?status=overdue").json()["results"]
    assert len(overdue) >= 1
    assert all(i["is_overdue"] for i in overdue)
    first = agreement["installments"][0]
    api_client.post(f"{INSTALLMENTS}{first['id']}/settle/", {"method": "DINHEIRO"}, format="json")
    summary = api_client.get(f"{INSTALLMENTS}summary/?month={today:%Y-%m}").json()
    assert Decimal(summary["received"]) == Decimal(first["amount"])
    assert summary["overdue_count"] >= 0
    assert api_client.get(f"{INSTALLMENTS}summary/?month=xx").status_code == 400


def test_other_office_cannot_see(tenant_a, tenant_b, ana, login, api_client):
    login(tenant_a.owner.email)
    agreement = _create(api_client, ana)
    api_client.credentials()
    login(tenant_b.owner.email)
    assert api_client.get(f"{AGREEMENTS}{agreement['id']}/").status_code == 404
    assert api_client.get(INSTALLMENTS).json()["results"] == []
    other = api_client.post(
        AGREEMENTS,
        {
            "client_id": str(ana.pk),
            "total_amount": "10",
            "installments_count": 1,
            "first_due": "2026-01-01",
        },
        format="json",
    )
    assert other.status_code == 400


# ---------------------------------------------------------------- Mercado Pago


def test_only_owner_connects_and_token_is_encrypted(tenant_a, login, api_client, mp):
    lawyer = User.objects.create_user(email="adv@a.test", password="senha-de-teste-123")
    Membership.objects.create(user=lawyer, tenant=tenant_a.tenant, role=Membership.Role.LAWYER)
    login("adv@a.test")
    assert api_client.put(MP, {"access_token": TOKEN}, format="json").status_code == 403
    assert api_client.get(MP).json()["connected"] is False

    api_client.credentials()
    login(tenant_a.owner.email)
    bad = api_client.put(MP, {"access_token": "APP_USR-errado"}, format="json")
    assert bad.json()["error"]["code"] == "mercadopago_invalid_token"
    wrong_format = api_client.put(MP, {"access_token": "abc"}, format="json")
    assert wrong_format.json()["error"]["code"] == "invalid_token_format"

    ok = api_client.put(MP, {"access_token": TOKEN}, format="json").json()
    assert ok["connected"] is True
    assert ok["nickname"] == "ESCRITORIO_TESTE"
    assert ok["webhook_ready"] is True
    with tenant_context(tenant_a.tenant.id):
        stored = MercadoPagoAccount.objects.get().access_token_encrypted
    assert TOKEN not in stored

    assert api_client.delete(MP).json()["connected"] is False


def _connect(tenant_a: Any, user: Any) -> None:
    services.connect_account(tenant_a.tenant.id, token=TOKEN, user=user)


def test_pix_charge_then_webhook_settles(
    tenant_a, ana, login, api_client, client, mp, django_capture_on_commit_callbacks
):
    login(tenant_a.owner.email)
    agreement = _create(api_client, ana)
    inst = agreement["installments"][0]

    not_connected = api_client.post(f"{INSTALLMENTS}{inst['id']}/charge/", {"kind": "PIX"})
    assert not_connected.json()["error"]["code"] == "mercadopago_not_connected"

    _connect(tenant_a, tenant_a.owner)
    charged = api_client.post(f"{INSTALLMENTS}{inst['id']}/charge/", {"kind": "PIX"}, format="json")
    assert charged.status_code == 200, charged.content
    body = charged.json()
    assert body["has_active_charge"] is True
    assert body["pix_code"].startswith("000201")
    created = mp.created[-1]
    assert created["external_reference"] == inst["id"]
    assert created["payer"].cpf_cnpj == "52998224725"
    assert created["notification_url"].startswith("https://app.tramitai.test/api/webhooks/")

    # Mesma cobrança de novo: reaproveita, não cria outra no MP.
    api_client.post(f"{INSTALLMENTS}{inst['id']}/charge/", {"kind": "PIX"}, format="json")
    assert len(mp.created) == 1

    with tenant_context(tenant_a.tenant.id):
        route = PaymentWebhookRoute.objects.get(tenant=tenant_a.tenant)
    payment_id = body["mp_payment_id"] if "mp_payment_id" in body else created["payment_id"]
    url = f"/api/webhooks/mercadopago/{route.token}/?type=payment&data.id={payment_id}"

    # Aviso com o pagamento ainda pendente: nada muda.
    with django_capture_on_commit_callbacks(execute=True):
        assert client.post(url).status_code == 200
    assert api_client.get(f"{INSTALLMENTS}{inst['id']}/").json()["status"] == "OPEN"

    mp.payments[payment_id] = Payment(
        payment_id=payment_id,
        status="approved",
        external_reference=inst["id"],
        amount=Decimal(inst["amount"]),
        date_approved=timezone.now(),
        payment_type="bank_transfer",
    )
    with django_capture_on_commit_callbacks(execute=True):
        client.post(
            f"/api/webhooks/mercadopago/{route.token}/",
            data={"type": "payment", "data": {"id": payment_id}},
            content_type="application/json",
        )
    paid = api_client.get(f"{INSTALLMENTS}{inst['id']}/").json()
    assert paid["status"] == "PAID"
    assert paid["method"] == "PIX"
    assert paid["settled_by_name"] == ""
    # Pago pelo MP não reabre por aqui.
    assert api_client.post(f"{INSTALLMENTS}{inst['id']}/reopen/").status_code == 400


def test_webhook_unknown_token_and_foreign_payment(tenant_a, ana, client, mp):
    assert (
        client.post("/api/webhooks/mercadopago/nao-existe/?type=payment&data.id=1").status_code
        == 404
    )
    _connect(tenant_a, tenant_a.owner)
    mp.payments["777"] = Payment(
        payment_id="777",
        status="approved",
        external_reference="venda-da-loja",
        amount=Decimal("10"),
        date_approved=None,
        payment_type="credit_card",
    )
    assert services.sync_payment(tenant_a.tenant.id, "777") == "foreign_payment"
    assert services.sync_payment(tenant_a.tenant.id, "999") == "not_found"


def test_webhook_cannot_settle_other_office_installment(tenant_a, tenant_b, ana, mp):
    """O escritório B não consegue dar baixa numa parcela do A usando o próprio token."""
    with tenant_atomic(tenant_a.tenant.id):
        agreement = services.create_agreement(
            user=tenant_a.owner,
            client=ana,
            title="X",
            total_amount=Decimal("100"),
            installments=1,
            first_due=date(2026, 1, 1),
        )
        target = agreement.installments.get()
    _connect(tenant_b, tenant_b.owner)
    mp.payments["555"] = Payment(
        payment_id="555",
        status="approved",
        external_reference=str(target.pk),
        amount=Decimal("100"),
        date_approved=None,
        payment_type="bank_transfer",
    )
    assert services.sync_payment(tenant_b.tenant.id, "555") == "unknown_installment"
    with tenant_context(tenant_a.tenant.id):
        assert Installment.objects.get(pk=target.pk).status == Installment.Status.OPEN


def test_mp_down_is_retryable_and_reported(tenant_a, ana, login, api_client, mp):
    _connect(tenant_a, tenant_a.owner)
    login(tenant_a.owner.email)
    inst = _create(api_client, ana)["installments"][0]
    mp.fail_next = MercadoPagoError("http_503", "fora", retryable=True)
    response = api_client.post(
        f"{INSTALLMENTS}{inst['id']}/charge/", {"kind": "LINK"}, format="json"
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "mercadopago_unavailable"
    link = api_client.post(f"{INSTALLMENTS}{inst['id']}/charge/", {"kind": "LINK"}, format="json")
    assert link.json()["payment_url"].startswith("https://mpago.la/")


# ---------------------------------------------------------------- WhatsApp


def test_send_charge_by_whatsapp_and_daily_reminders(
    tenant_a, ana, account_a, inbound, login, api_client, mp
):
    inbound("Oi, pode mandar o Pix?")  # abre a janela de 24h da Meta
    _connect(tenant_a, tenant_a.owner)
    login(tenant_a.owner.email)
    today = timezone.localdate()
    agreement = _create(
        api_client, ana, first_due=(today + timedelta(days=3)).isoformat(), installments_count=2
    )
    inst = agreement["installments"][0]
    api_client.post(f"{INSTALLMENTS}{inst['id']}/charge/", {"kind": "PIX"}, format="json")
    sent = api_client.post(f"{INSTALLMENTS}{inst['id']}/send-whatsapp/")
    assert sent.status_code == 202

    from apps.whatsapp.models import Message

    with tenant_context(tenant_a.tenant.id):
        message = Message.objects.filter(direction="OUT").latest("created_at")
    assert "Pix copia e cola" in message.body
    assert "R$ 500,00" in message.body

    # Já lembrado hoje (envio manual): o beat não cria rascunho repetido.
    assert services.create_payment_reminders() == 0
    with tenant_atomic(tenant_a.tenant.id):
        Installment.objects.filter(pk=inst["id"]).update(last_reminder_on=today - timedelta(days=1))
    assert services.create_payment_reminders() == 1
    with tenant_context(tenant_a.tenant.id):
        draft = OutboundDraft.objects.get(origin=OutboundDraft.Origin.PAYMENT_REMINDER)
    assert draft.status == OutboundDraft.Status.DRAFT  # só sai com aprovação
    assert "vence em breve" in draft.generated_body


def test_cancel_agreement_cancels_open_installments(tenant_a, ana, login, api_client):
    login(tenant_a.owner.email)
    agreement = _create(api_client, ana)
    api_client.post(
        f"{INSTALLMENTS}{agreement['installments'][0]['id']}/settle/",
        {"method": "PIX"},
        format="json",
    )
    cancelled = api_client.post(f"{AGREEMENTS}{agreement['id']}/cancel/").json()
    assert cancelled["status"] == "CANCELLED"
    assert [i["status"] for i in cancelled["installments"]] == ["PAID", "CANCELLED", "CANCELLED"]
    with tenant_context(tenant_a.tenant.id):
        assert FeeAgreement.objects.get().status == FeeAgreement.Status.CANCELLED

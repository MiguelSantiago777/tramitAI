"""Painel da plataforma: só o dono do TramitAI, só números (nunca conteúdo), ações auditadas."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.clientes.models import Client
from apps.cobranca import services
from apps.cobranca.models import Plan, Subscription, SubscriptionPayment
from apps.core.mercadopago import AuthorizedPayment, FakeMercadoPago, get_mercadopago
from apps.core.models import AuditEvent
from apps.core.tenancy import tenant_atomic, tenant_context
from apps.tenants.models import Tenant

P = "/api/v1/platform/"


@pytest.fixture
def admin(tenant_a, login, api_client):
    User.objects.filter(pk=tenant_a.owner.pk).update(is_superuser=True, is_staff=True)
    login(tenant_a.owner.email)
    return api_client


@pytest.fixture
def trial_office(tenant_b):
    sub = Subscription.objects.create(
        tenant=tenant_b.tenant,
        plan=Plan.objects.get(code="escritorio"),
        status=Subscription.Status.TRIAL,
        trial_ends_at=timezone.now() + timedelta(days=3),
    )
    with tenant_atomic(tenant_b.tenant.id):
        Client.objects.create(name="Cliente Sigiloso da Silva")
    return sub


def test_only_superuser_gets_in(tenant_a, tenant_b, login, api_client):
    login(tenant_a.owner.email)
    for url in ("overview/", "offices/", "payments/", "plans/"):
        assert api_client.get(P + url).status_code == 403
    assert (
        api_client.post(f"{P}offices/{tenant_b.tenant.id}/exempt/", {"exempt": True}).status_code
        == 403
    )
    assert api_client.get("/api/v1/auth/me/").json()["is_platform_admin"] is False


def test_overview_and_office_list_show_numbers_not_content(admin, tenant_a, tenant_b, trial_office):
    assert admin.get("/api/v1/auth/me/").json()["is_platform_admin"] is True
    overview = admin.get(P + "overview/").json()
    assert overview["offices"] == 2
    assert overview["by_status"] == {"EXEMPT": 1, "TRIAL": 1}
    assert [o["name"] for o in overview["trials_ending"]] == [tenant_b.tenant.name]

    offices = admin.get(P + "offices/").json()
    row = next(o for o in offices if o["id"] == str(tenant_b.tenant.id))
    assert row["usage"]["clients"] == 1
    assert row["owner_email"] == tenant_b.owner.email
    # Sigilo: nenhum dado de cliente do escritório sai no painel.
    assert "Cliente Sigiloso" not in str(offices)
    assert "Cliente Sigiloso" not in str(admin.get(f"{P}offices/{tenant_b.tenant.id}/").json())


def test_actions_change_access_and_are_audited(admin, tenant_a, tenant_b, trial_office):
    office = f"{P}offices/{tenant_b.tenant.id}/"
    before = trial_office.trial_ends_at
    admin.post(office + "extend-trial/", {"days": 10})
    trial_office.refresh_from_db()
    assert trial_office.trial_ends_at - before >= timedelta(days=9, hours=23)

    paid = admin.post(
        office + "manual-payment/", {"amount": "197.00", "months": 2, "note": "Pix direto"}
    ).json()
    assert paid["status"] == "ACTIVE"
    assert paid["payments"][0]["source"] == "MANUAL"
    trial_office.refresh_from_db()
    assert trial_office.paid_until > timezone.now() + timedelta(days=55)

    admin.post(office + "exempt/", {"exempt": True})
    assert admin.get(office).json()["status"] == "EXEMPT"
    admin.post(office + "suspend/", {"suspended": True})
    assert Tenant.objects.get(pk=tenant_b.tenant.id).status == Tenant.Status.SUSPENDED
    detail = admin.get(office).json()
    assert detail["status"] == "SUSPENDED"
    actions = [h["action"] for h in detail["history"]]
    assert {"platform.trial_extended", "platform.manual_payment", "platform.suspended"} <= set(
        actions
    )
    with tenant_context(tenant_b.tenant.id):
        assert AuditEvent.objects.filter(action="platform.exempt_on").exists()

    # Escritório bloqueado: titular não entra mais.
    admin.credentials()
    blocked = admin.post(
        "/api/v1/auth/login/",
        {"email": tenant_b.owner.email, "password": "senha-de-teste-123"},
        format="json",
    )
    assert blocked.status_code == 403


def test_cannot_suspend_own_office(admin, tenant_a):
    response = admin.post(f"{P}offices/{tenant_a.tenant.id}/suspend/", {"suspended": True})
    assert response.json()["error"]["code"] == "own_office"


def test_plans_crud_without_delete(admin):
    created = admin.post(
        P + "plans/", {"code": "anual", "name": "Anual", "price": "1970.00"}, format="json"
    )
    assert created.status_code == 201
    plan_id = created.json()["id"]
    assert admin.patch(f"{P}plans/{plan_id}/", {"price": "1790.00"}).json()["price"] == "1790.00"
    assert admin.delete(f"{P}plans/{plan_id}/").status_code == 405


def test_mercadopago_charge_is_recorded_once(db, tenant_b, settings):
    settings.MERCADOPAGO_PLATFORM_TOKEN = "APP_USR-teste"
    mp = get_mercadopago()
    assert isinstance(mp, FakeMercadoPago)
    sub = Subscription.objects.create(
        tenant=tenant_b.tenant, status=Subscription.Status.PENDING, mp_preapproval_id="pre-1"
    )
    charge = AuthorizedPayment(
        payment_id="ap-1",
        preapproval_id="pre-1",
        status="processed",
        amount=Decimal("197.00"),
        date=timezone.now(),
    )
    services.record_payment(charge)
    services.record_payment(charge)  # aviso repetido
    assert SubscriptionPayment.objects.filter(subscription=sub).count() == 1
    assert (
        services.record_payment(
            AuthorizedPayment("ap-2", "pre-1", "scheduled", Decimal("197"), None)
        )
        is None
    )  # agendada: ainda não é pagamento


def test_removing_exemption_gives_default_plan_and_a_week_to_pay(admin, tenant_b):
    office = f"{P}offices/{tenant_b.tenant.id}/"
    admin.post(office + "exempt/", {"exempt": True}, format="json")
    detail = admin.post(office + "exempt/", {"exempt": False}, format="json").json()
    assert detail["status"] == "TRIAL"
    assert detail["plan_code"] == "escritorio"
    sub = Subscription.objects.get(tenant=tenant_b.tenant)
    assert sub.trial_ends_at is not None
    assert timedelta(days=6) < sub.trial_ends_at - timezone.now() <= timedelta(days=7)

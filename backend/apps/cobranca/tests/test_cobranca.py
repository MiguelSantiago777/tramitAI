"""Assinatura do TramitAI: cadastro com teste grátis, bloqueio, checkout e aviso do MP."""

from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.cobranca.models import Plan, Subscription
from apps.cobranca.services import sync_subscription
from apps.core.mercadopago import FakeMercadoPago, get_mercadopago
from apps.core.mercadopago import Subscription as MpSubscription
from apps.tenants.models import Tenant

SIGNUP = "/api/v1/auth/signup/"
BILLING = "/api/v1/billing/"
TOKEN = "APP_USR-teste"


@pytest.fixture
def mp(settings: Any) -> FakeMercadoPago:
    settings.MERCADOPAGO_PLATFORM_TOKEN = TOKEN
    client = get_mercadopago()
    assert isinstance(client, FakeMercadoPago)
    client.subscriptions.clear()
    client.created.clear()
    client.cancelled.clear()
    client.fail_next = None
    return client


def _signup(api_client: Any, **extra: Any) -> Any:
    body = {
        "office_name": "Souza Advocacia",
        "full_name": "Bia Souza",
        "email": "bia@souza.adv.br",
        "password": "uma-senha-bem-forte-123",
        "accept_terms": True,
        **extra,
    }
    return api_client.post(SIGNUP, body, format="json")


def test_signup_creates_office_in_trial_and_logs_in(db, api_client):
    response = _signup(api_client)
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["session"]["role"] == "OWNER"
    assert body["session"]["tenant"]["name"] == "Souza Advocacia"

    tenant = Tenant.objects.get(name="Souza Advocacia")
    sub = Subscription.objects.get(tenant=tenant)
    assert sub.status == Subscription.Status.TRIAL
    assert sub.plan is not None
    assert sub.plan.code == "escritorio"
    assert sub.trial_ends_at is not None
    assert (sub.trial_ends_at - timezone.now()).days >= 13

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {body['access']}")
    billing = api_client.get(BILLING).json()
    assert billing["status"] == "TRIAL"
    assert billing["blocked"] is False
    assert billing["days_left"] == 14
    assert api_client.get("/api/v1/clients/").status_code == 200


def test_signup_rules(db, api_client, settings):
    assert _signup(api_client, accept_terms=False).status_code == 400
    assert _signup(api_client, password="123").status_code == 400
    assert _signup(api_client).status_code == 201
    taken = _signup(api_client, office_name="Outro")
    assert taken.status_code == 409
    assert taken.json()["error"]["code"] == "email_taken"
    # Mesmo nome de escritório: slug diferente, sem erro.
    assert _signup(api_client, email="outra@souza.adv.br").status_code == 201
    settings.SIGNUP_ENABLED = False
    assert _signup(api_client, email="x@y.com.br").status_code == 403


def test_expired_trial_blocks_api_but_not_billing(db, api_client):
    body = _signup(api_client).json()
    Subscription.objects.update(trial_ends_at=timezone.now() - timedelta(minutes=1))
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {body['access']}")

    blocked = api_client.get("/api/v1/clients/")
    assert blocked.status_code == 402
    assert blocked.json()["error"]["code"] == "subscription_required"
    assert api_client.get("/api/v1/auth/me/").status_code == 200
    billing = api_client.get(BILLING)
    assert billing.status_code == 200
    assert billing.json()["blocked"] is True


def test_existing_offices_are_exempt(tenant_a, login, api_client):
    """Escritório sem linha de assinatura (criado pelo admin/antes) nunca é bloqueado."""
    login(tenant_a.owner.email)
    assert api_client.get(BILLING).json()["exempt"] is True
    assert api_client.get("/api/v1/clients/").status_code == 200


def test_checkout_then_webhook_activates(
    db, api_client, client, mp, django_capture_on_commit_callbacks
):
    Plan.objects.filter(code="escritorio").update(price="149.90")
    body = _signup(api_client).json()
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {body['access']}")

    checkout = api_client.post(BILLING, {"payer_email": "pagador@email.com"}, format="json")
    assert checkout.status_code == 200, checkout.content
    assert "preapproval_id=" in checkout.json()["checkout_url"]
    created = mp.created[-1]
    tenant = Tenant.objects.get(name="Souza Advocacia")
    assert created["external_reference"] == str(tenant.id)
    assert str(created["amount"]) == "149.90"
    assert created["back_url"].endswith("/assinatura?retorno=1")
    sub = Subscription.objects.get(tenant=tenant)
    assert sub.status == Subscription.Status.PENDING

    # Cliente pagou no MP: o aviso faz a gente consultar e liberar.
    next_charge = timezone.now() + timedelta(days=30)
    mp.subscriptions[sub.mp_preapproval_id] = MpSubscription(
        preapproval_id=sub.mp_preapproval_id,
        status="authorized",
        external_reference=str(tenant.id),
        init_point="",
        next_payment_date=next_charge,
    )
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            "/api/webhooks/mercadopago-assinatura/",
            data={"type": "subscription_preapproval", "data": {"id": sub.mp_preapproval_id}},
            content_type="application/json",
        )
    assert response.status_code == 200
    sub.refresh_from_db()
    assert sub.status == Subscription.Status.ACTIVE
    assert sub.paid_until == next_charge

    # Trial venceu, mas está pago: segue liberado.
    Subscription.objects.update(trial_ends_at=timezone.now() - timedelta(days=1))
    assert api_client.get("/api/v1/clients/").status_code == 200

    # Pagamento parou e passou a tolerância: bloqueia.
    Subscription.objects.update(paid_until=timezone.now() - timedelta(days=6))
    assert api_client.get("/api/v1/clients/").status_code == 402


def test_webhook_cannot_activate_other_tenant(db, api_client, mp):
    body = _signup(api_client).json()
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {body['access']}")
    api_client.post(BILLING, {"payer_email": "p@e.com"}, format="json")
    sub = Subscription.objects.get()
    # Assinatura de outra conta/empresa no MP: referência não é um escritório nosso.
    mp.subscriptions["preapp-alheio"] = MpSubscription(
        preapproval_id="preapp-alheio",
        status="authorized",
        external_reference="loja-qualquer",
        init_point="",
        next_payment_date=None,
    )
    assert sync_subscription("preapp-alheio") == "foreign"
    # Checkout antigo de um escritório, não pago: não mexe.
    mp.subscriptions["preapp-velho"] = MpSubscription(
        preapproval_id="preapp-velho",
        status="pending",
        external_reference=str(sub.tenant_id),
        init_point="",
        next_payment_date=None,
    )
    assert sync_subscription("preapp-velho") == "stale"
    sub.refresh_from_db()
    assert sub.status == Subscription.Status.PENDING


def test_only_owner_subscribes_and_billing_not_configured(db, api_client, settings):
    body = _signup(api_client).json()
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {body['access']}")
    settings.MERCADOPAGO_PLATFORM_TOKEN = ""
    response = api_client.post(BILLING, {"payer_email": "p@e.com"}, format="json")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "billing_not_configured"


def test_public_plans(db, api_client):
    plans = api_client.get("/api/v1/billing/plans/").json()
    assert [p["code"] for p in plans] == ["escritorio"]

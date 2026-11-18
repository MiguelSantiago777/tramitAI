"""Limites do plano: usuários, mensagens da Lia no mês e troca de plano pelo escritório."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.cobranca import limits
from apps.cobranca.models import Plan, Subscription
from apps.core.mercadopago import FakeMercadoPago, get_mercadopago
from apps.core.tenancy import tenant_atomic
from apps.ia.models import AiGeneration

TEAM = "/api/v1/tenant/team/"
BILLING = "/api/v1/billing/"


@pytest.fixture
def essencial(tenant_a):
    """Escritório A no plano Essencial (2 usuários, 300 da Lia), em teste."""
    return Subscription.objects.create(
        tenant=tenant_a.tenant,
        plan=Plan.objects.get(code="essencial"),
        status=Subscription.Status.TRIAL,
        trial_ends_at=timezone.now() + timedelta(days=10),
    )


def _invite(api_client, email):
    return api_client.post(
        TEAM, {"email": email, "full_name": "Fulana", "role": "STAFF"}, format="json"
    )


def _lia(tenant_id, n, status=AiGeneration.Status.OK, when=None):
    with tenant_atomic(tenant_id):
        for _ in range(n):
            g = AiGeneration.objects.create(
                kind=AiGeneration.Kind.TRIAGE,
                status=status,
                prompt_name="triage",
                prompt_version="v3",
                provider="fake",
            )
            if when:
                AiGeneration.objects.filter(pk=g.pk).update(created_at=when)


def test_three_tiers_are_offered(db, api_client):
    plans = api_client.get("/api/v1/billing/plans/").json()
    assert [(p["code"], p["max_users"], p["monthly_ai_limit"]) for p in plans] == [
        ("essencial", 2, 300),
        ("escritorio", 5, 1000),
        ("equipe", 15, 3000),
    ]


def test_user_limit_blocks_new_invites(tenant_a, essencial, login, api_client):
    login(tenant_a.owner.email)
    assert _invite(api_client, "segunda@exemplo.com").status_code == 201  # 2 de 2
    response = _invite(api_client, "terceira@exemplo.com")
    assert response.status_code == 402
    assert "Essencial" in response.json()["error"]["message"]


def test_reactivating_member_counts_as_a_seat(tenant_a, essencial, login, api_client):
    login(tenant_a.owner.email)
    member_id = _invite(api_client, "segunda@exemplo.com").json()["id"]
    api_client.patch(f"{TEAM}{member_id}/", {"is_active": False}, format="json")
    assert _invite(api_client, "terceira@exemplo.com").status_code == 201
    response = api_client.patch(f"{TEAM}{member_id}/", {"is_active": True}, format="json")
    assert response.status_code == 402


def test_exempt_office_has_no_limits(tenant_a, essencial):
    essencial.status = Subscription.Status.EXEMPT
    essencial.save()
    _lia(tenant_a.tenant.id, 3)
    Plan.objects.filter(code="essencial").update(monthly_ai_limit=2, max_users=0)
    with tenant_atomic(tenant_a.tenant.id):
        assert limits.ai_allowed(tenant_a.tenant.id)
        limits.check_can_add_user(tenant_a.tenant.id)


def test_lia_stops_at_monthly_limit_and_only_this_month_counts(tenant_a, essencial):
    Plan.objects.filter(code="essencial").update(monthly_ai_limit=3)
    tid = tenant_a.tenant.id
    _lia(tid, 5, when=limits.month_start() - timedelta(hours=1))  # mês passado
    _lia(tid, 4, status=AiGeneration.Status.ERROR)  # falha do provedor não conta
    _lia(tid, 2)
    with tenant_atomic(tid):
        assert limits.ai_allowed(tid)
        assert limits.usage(tid).ai_warning is False
    _lia(tid, 1)
    with tenant_atomic(tid):
        assert not limits.ai_allowed(tid)
        assert limits.usage(tid).ai_exhausted


def test_billing_shows_usage(tenant_a, essencial, login, api_client):
    _lia(tenant_a.tenant.id, 7)
    login(tenant_a.owner.email)
    body = api_client.get(BILLING).json()
    assert body["plan_code"] == "essencial"
    assert (body["users_used"], body["users_limit"]) == (1, 2)
    assert (body["ai_used"], body["ai_limit"]) == (7, 300)


def test_change_plan_during_trial(tenant_a, essencial, login, api_client):
    login(tenant_a.owner.email)
    body = api_client.post(f"{BILLING}plan/", {"plan_code": "equipe"}, format="json").json()
    assert body["plan_code"] == "equipe"
    assert body["users_limit"] == 15


def test_change_plan_of_paid_subscription_updates_mercadopago(
    tenant_a, essencial, login, api_client, settings
):
    settings.MERCADOPAGO_PLATFORM_TOKEN = "APP_USR-teste"
    mp = get_mercadopago()
    assert isinstance(mp, FakeMercadoPago)
    mp.amount_updates.clear()
    essencial.status = Subscription.Status.ACTIVE
    essencial.mp_preapproval_id = "pre-9"
    essencial.save()
    login(tenant_a.owner.email)
    response = api_client.post(f"{BILLING}plan/", {"plan_code": "escritorio"}, format="json")
    assert response.status_code == 200, response.content
    assert mp.amount_updates == [("pre-9", Decimal("297.00"))]
    assert Subscription.objects.get(pk=essencial.pk).plan == Plan.objects.get(code="escritorio")


def test_cannot_downgrade_below_current_team(tenant_a, login, api_client):
    Subscription.objects.create(
        tenant=tenant_a.tenant,
        plan=Plan.objects.get(code="escritorio"),
        status=Subscription.Status.TRIAL,
        trial_ends_at=timezone.now() + timedelta(days=10),
    )
    login(tenant_a.owner.email)
    _invite(api_client, "b@exemplo.com")
    _invite(api_client, "c@exemplo.com")
    response = api_client.post(f"{BILLING}plan/", {"plan_code": "essencial"}, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "plan_user_limit"

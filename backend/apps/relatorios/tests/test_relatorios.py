from datetime import date
from decimal import Decimal

from django.utils import timezone

from apps.accounts.models import Membership, User
from apps.clientes.models import Client
from apps.core.tenancy import tenant_atomic
from apps.financeiro import services as finance
from apps.funil.models import Opportunity

URL = "/api/v1/reports/overview/"


def test_overview_counts_period_and_isolates_offices(tenant_a, tenant_b, login, api_client):
    with tenant_atomic(tenant_a.tenant.id):
        ana = Client.objects.create(name="Ana")
        Client.objects.create(name="Lead", status=Client.Status.LEAD)
        Opportunity.objects.create(
            title="Caso",
            client=ana,
            stage=Opportunity.Stage.WON,
            closed_at=timezone.now(),
            estimated_value=Decimal("3000"),
        )
        agreement = finance.create_agreement(
            user=tenant_a.owner,
            client=ana,
            title="Honorários",
            total_amount=Decimal("1000"),
            installments=2,
            first_due=timezone.localdate(),
        )
        first = agreement.installments.order_by("number").first()
        assert first is not None
        finance.settle(first, user=tenant_a.owner, method="PIX")
    with tenant_atomic(tenant_b.tenant.id):
        Client.objects.create(name="Do B")

    login(tenant_a.owner.email)
    body = api_client.get(URL).json()
    assert body["clients"]["new_clients"] == 1
    assert body["clients"]["new_leads"] == 1
    assert body["funnel"]["won"] == 1
    assert body["funnel"]["conversion"] == 100.0
    assert Decimal(body["finance"]["received"]) == Decimal("500.00")
    assert len(body["finance_months"]) == 6
    assert Decimal(body["finance_months"][-1]["received"]) == Decimal("500.00")


def test_overview_validation_and_staff(tenant_a, login, api_client):
    login(tenant_a.owner.email)
    assert api_client.get(f"{URL}?start=2026-02-01&end=2026-01-01").status_code == 400
    assert api_client.get(f"{URL}?start=2024-01-01&end=2026-01-01").status_code == 400
    ok = api_client.get(f"{URL}?start=2026-01-01&end=2026-01-31").json()
    assert ok["start"] == date(2026, 1, 1).isoformat()

    staff = User.objects.create_user(email="equipe@a.test", password="senha-de-teste-123")
    Membership.objects.create(user=staff, tenant=tenant_a.tenant, role=Membership.Role.STAFF)
    api_client.credentials()
    login("equipe@a.test")
    assert api_client.get(URL).status_code == 403

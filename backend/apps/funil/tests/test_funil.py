from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.clientes.models import Client
from apps.clientes.services import register_term_acceptance
from apps.core.models import AuditEvent
from apps.core.tenancy import tenant_context
from apps.funil.models import Opportunity

URL = "/api/v1/opportunities/"


@pytest.fixture
def ana(tenant_a):
    with tenant_context(tenant_a.tenant.id):
        return Client.objects.create(name="Ana Souza", status=Client.Status.LEAD)


def _opps(tenant_a, **filters):
    with tenant_context(tenant_a.tenant.id):
        return list(Opportunity.objects.filter(**filters).order_by("stage", "position"))


def test_create_with_existing_client(tenant_a, ana, login, api_client):
    login(tenant_a.owner.email)
    response = api_client.post(
        URL,
        {
            "title": "Demissão sem justa causa",
            "client_id": str(ana.pk),
            "area": "TRABALHISTA",
            "source": "INDICACAO",
            "estimated_value": "3500.00",
        },
        format="json",
    )
    assert response.status_code == 201, response.json()
    body = response.json()
    assert (body["stage"], body["client_name"], body["position"]) == ("NEW", "Ana Souza", 0)


def test_create_new_lead_from_board(tenant_a, login, api_client):
    login(tenant_a.owner.email)
    response = api_client.post(
        URL,
        {"new_client_name": "Carlos Lima", "new_client_phone": "(21) 99111-2233"},
        format="json",
    )
    assert response.status_code == 201, response.json()
    assert response.json()["title"] == "Caso de Carlos Lima"
    with tenant_context(tenant_a.tenant.id):
        carlos = Client.objects.get(name="Carlos Lima")
    assert (carlos.status, carlos.phone_e164) == (Client.Status.LEAD, "+5521991112233")


def test_create_requires_client(tenant_a, login, api_client):
    login(tenant_a.owner.email)
    response = api_client.post(URL, {"title": "x"}, format="json")
    assert response.status_code == 400
    assert "client_id" in response.json()["error"]["details"]


def test_cannot_use_client_from_other_office(tenant_a, tenant_b, login, api_client):
    with tenant_context(tenant_b.tenant.id):
        other = Client.objects.create(name="Do B")
    login(tenant_a.owner.email)
    response = api_client.post(URL, {"client_id": str(other.pk)}, format="json")
    assert response.status_code == 400


def test_move_reorders_columns_and_audits(tenant_a, ana, login, api_client):
    login(tenant_a.owner.email)
    ids = [
        api_client.post(URL, {"client_id": str(ana.pk), "title": t}, format="json").json()["id"]
        for t in ("primeira", "segunda", "terceira")
    ]
    # Mais nova no topo: terceira(0), segunda(1), primeira(2).
    moved = api_client.post(
        f"{URL}{ids[1]}/move/", {"stage": "CONSULT", "position": 0}, format="json"
    ).json()
    assert (moved["stage"], moved["position"]) == ("CONSULT", 0)
    new_col = [o.title for o in _opps(tenant_a, stage="NEW")]
    assert new_col == ["terceira", "primeira"]
    assert [o.position for o in _opps(tenant_a, stage="NEW")] == [0, 1]

    api_client.post(f"{URL}{ids[0]}/move/", {"stage": "NEW", "position": 0}, format="json")
    assert [o.title for o in _opps(tenant_a, stage="NEW")] == ["primeira", "terceira"]
    with tenant_context(tenant_a.tenant.id):
        assert AuditEvent.objects.filter(action="opportunity.stage_changed").count() == 1


def test_lost_requires_reason_and_won_activates_lead(tenant_a, ana, login, api_client):
    login(tenant_a.owner.email)
    opp = api_client.post(URL, {"client_id": str(ana.pk)}, format="json").json()

    no_reason = api_client.post(f"{URL}{opp['id']}/move/", {"stage": "LOST"}, format="json")
    assert no_reason.json()["error"]["code"] == "lost_reason_required"

    lost = api_client.post(
        f"{URL}{opp['id']}/move/", {"stage": "LOST", "lost_reason": "Achou caro"}, format="json"
    ).json()
    assert lost["closed_at"]
    assert lost["lost_reason"] == "Achou caro"

    won = api_client.post(f"{URL}{opp['id']}/move/", {"stage": "WON"}, format="json").json()
    assert won["lost_reason"] == ""
    with tenant_context(tenant_a.tenant.id):
        assert Client.objects.get(pk=ana.pk).status == Client.Status.ACTIVE

    reopened = api_client.post(f"{URL}{opp['id']}/move/", {"stage": "NEW"}, format="json").json()
    assert reopened["closed_at"] is None


def test_board_hides_old_closed_and_filters_owner(tenant_a, ana, login, api_client):
    with tenant_context(tenant_a.tenant.id):
        Opportunity.objects.create(title="aberta minha", client=ana, owner=tenant_a.owner)
        Opportunity.objects.create(title="aberta sem dono", client=ana)
        Opportunity.objects.create(
            title="fechada antiga",
            client=ana,
            stage=Opportunity.Stage.LOST,
            closed_at=timezone.now() - timedelta(days=60),
        )
    login(tenant_a.owner.email)
    titles = {o["title"] for o in api_client.get(URL).json()}
    assert titles == {"aberta minha", "aberta sem dono"}
    mine = {o["title"] for o in api_client.get(f"{URL}?owner=me").json()}
    assert mine == {"aberta minha"}
    assert len(api_client.get(f"{URL}?closed_days=90").json()) == 3


def test_summary_numbers(tenant_a, ana, login, api_client):
    now = timezone.now()
    with tenant_context(tenant_a.tenant.id):
        Opportunity.objects.create(title="a", client=ana, estimated_value=Decimal("1000"))
        Opportunity.objects.create(
            title="b", client=ana, stage=Opportunity.Stage.CONSULT, estimated_value=Decimal("500")
        )
        Opportunity.objects.create(
            title="c",
            client=ana,
            stage=Opportunity.Stage.WON,
            closed_at=now,
            estimated_value=Decimal("2000"),
        )
        Opportunity.objects.create(
            title="d", client=ana, stage=Opportunity.Stage.LOST, closed_at=now
        )
    login(tenant_a.owner.email)
    summary = api_client.get(f"{URL}summary/").json()
    assert summary["open_count"] == 2
    assert summary["by_stage"] == {"NEW": 1, "TRIAGE": 0, "CONSULT": 1, "PROPOSAL": 0}
    assert Decimal(summary["open_value"]) == Decimal("1500")
    assert (summary["won_count"], summary["lost_count"]) == (1, 1)
    assert summary["conversion_rate"] == 0.5


def test_other_office_cannot_see_board(tenant_a, tenant_b, ana, login, api_client):
    with tenant_context(tenant_a.tenant.id):
        opp = Opportunity.objects.create(title="segredo", client=ana)
    login(tenant_b.owner.email)
    assert api_client.get(URL).json() == []
    assert (
        api_client.post(f"{URL}{opp.pk}/move/", {"stage": "WON"}, format="json").status_code == 404
    )


def test_triage_new_matter_enters_funnel_once(tenant_a, account_a, inbound, fake_llm):
    with tenant_context(tenant_a.tenant.id):
        maria = Client.objects.create(name="Maria Lead", phone_e164="+5521998765432")
        register_term_acceptance(client=maria, channel="IN_PERSON")
    new_matter = {
        "intent": "new_matter",
        "needs_lawyer": True,
        "urgency": "normal",
        "summary_for_lawyer": "Foi demitida e não recebeu as verbas.",
        "reply": "Entendi! Vou passar para o advogado.",
    }
    fake_llm.queue.extend([new_matter, dict(new_matter)])
    inbound("Fui demitida e não recebi nada, vocês podem me ajudar?")
    inbound("Trabalhei 3 anos lá")

    [opp] = _opps(tenant_a)
    assert opp.source == Opportunity.Source.WHATSAPP
    assert opp.stage == Opportunity.Stage.NEW
    assert opp.notes == "Foi demitida e não recebeu as verbas."
    assert opp.conversation_id is not None

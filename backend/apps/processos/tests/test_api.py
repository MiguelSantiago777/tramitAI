import pytest

from apps.accounts.models import Membership, User
from apps.processos.cnj import format_cnj

from .factories import make_cnj

pytestmark = pytest.mark.django_db

URL = "/api/v1/cases/"


@pytest.fixture
def as_a(tenant_a, login):
    login(tenant_a.owner.email)
    return tenant_a


@pytest.fixture
def client_id(as_a, api_client):
    response = api_client.post("/api/v1/clients/", {"name": "Maria da Silva"}, format="json")
    return response.json()["id"]


def _create(api_client, **overrides):
    body = {"cnj_number": format_cnj(make_cnj()), "classe": "Procedimento Comum Cível"}
    body.update(overrides)
    return api_client.post(URL, body, format="json")


def test_create_with_formatted_cnj_and_client(as_a, api_client, client_id):
    response = _create(api_client, clients=[{"client_id": client_id, "role": "AUTHOR"}])
    assert response.status_code == 201
    body = response.json()
    assert body["cnj_number"] == make_cnj()
    assert body["cnj_formatted"] == format_cnj(make_cnj())
    assert body["tribunal"] == "TJRJ"
    assert body["monitoring_enabled"] is True
    assert body["clients"] == [
        {"client_id": client_id, "client_name": "Maria da Silva", "role": "AUTHOR"}
    ]


def test_invalid_cnj(as_a, api_client):
    digits = make_cnj()
    wrong = digits[:7] + "00" + digits[9:]
    response = _create(api_client, cnj_number=wrong)
    assert response.status_code == 400
    assert "Número CNJ inválido" in response.json()["error"]["details"]["cnj_number"][0]


def test_duplicate_cnj(as_a, api_client):
    assert _create(api_client).status_code == 201
    response = _create(api_client, cnj_number=make_cnj())
    assert response.status_code == 400
    assert response.json()["error"]["details"]["cnj_number"] == [
        "Este processo já está cadastrado."
    ]


def test_cannot_link_client_from_another_tenant(tenant_a, tenant_b, login, api_client):
    login(tenant_b.owner.email)
    foreign_id = api_client.post("/api/v1/clients/", {"name": "Do B"}, format="json").json()["id"]

    login(tenant_a.owner.email)
    response = _create(api_client, clients=[{"client_id": foreign_id, "role": "AUTHOR"}])
    assert response.status_code == 400
    assert "clients" in response.json()["error"]["details"]


def test_duplicate_client_in_links(as_a, api_client, client_id):
    links = [{"client_id": client_id}, {"client_id": client_id, "role": "OTHER"}]
    response = _create(api_client, clients=links)
    assert response.status_code == 400


def test_responsible_must_be_member_of_tenant(tenant_a, tenant_b, login, api_client):
    login(tenant_a.owner.email)
    ok = _create(api_client, responsible_id=str(tenant_a.owner.id))
    assert ok.status_code == 201
    assert ok.json()["responsible_name"] == tenant_a.owner.email

    response = _create(
        api_client, cnj_number=make_cnj(sequence=2), responsible_id=str(tenant_b.owner.id)
    )
    assert response.status_code == 400
    assert "responsible_id" in response.json()["error"]["details"]


def test_update_replaces_client_links_only_when_sent(as_a, api_client, client_id):
    other = api_client.post("/api/v1/clients/", {"name": "João"}, format="json").json()["id"]
    case_id = _create(api_client, clients=[{"client_id": client_id}]).json()["id"]

    response = api_client.patch(f"{URL}{case_id}/", {"assunto": "Danos morais"}, format="json")
    assert [c["client_id"] for c in response.json()["clients"]] == [client_id]

    response = api_client.patch(
        f"{URL}{case_id}/",
        {"clients": [{"client_id": other, "role": "DEFENDANT"}]},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["clients"] == [
        {"client_id": other, "client_name": "João", "role": "DEFENDANT"}
    ]


def test_search_by_cnj_fragment_and_client_name(as_a, api_client, client_id):
    _create(api_client, clients=[{"client_id": client_id}])
    _create(api_client, cnj_number=make_cnj(sequence=5550001, court="26"), classe="Execução")

    def cnjs(**params):
        return [c["tribunal"] for c in api_client.get(URL, params).json()["results"]]

    assert cnjs(q="maria") == ["TJRJ"]
    assert cnjs(q="5550001") == ["TJSP"]
    assert cnjs(client_id=client_id) == ["TJRJ"]
    assert len(cnjs()) == 2


def test_other_tenant_cannot_see_case(tenant_a, tenant_b, login, api_client):
    login(tenant_a.owner.email)
    case_id = _create(api_client).json()["id"]

    login(tenant_b.owner.email)
    assert api_client.get(f"{URL}{case_id}/").status_code == 404
    assert api_client.get(URL).json()["count"] == 0
    # O mesmo número pode existir em outro escritório.
    assert _create(api_client).status_code == 201


def test_staff_can_manage_cases(tenant_a, login, api_client):
    staff = User.objects.create_user(email="equipe@a.test", password="senha-de-teste-123")
    Membership.objects.create(user=staff, tenant=tenant_a.tenant, role=Membership.Role.STAFF)
    login("equipe@a.test")
    assert _create(api_client).status_code == 201

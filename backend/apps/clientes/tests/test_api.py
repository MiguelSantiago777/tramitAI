import pytest

from apps.clientes.models import Client, ClientTermAcceptance
from apps.core.tenancy import tenant_context
from apps.tenants.services import publish_term_version

pytestmark = pytest.mark.django_db

URL = "/api/v1/clients/"
CPF = "529.982.247-25"


def _create(api_client, **overrides):
    body = {"name": "Maria da Silva", "kind": "PF", "cpf_cnpj": CPF, "phone": "(21) 99876-5432"}
    body.update(overrides)
    return api_client.post(URL, body, format="json")


@pytest.fixture
def as_a(tenant_a, login):
    login(tenant_a.owner.email)
    return tenant_a


def test_create_normalizes_document_and_phone(as_a, api_client):
    response = _create(api_client)
    assert response.status_code == 201
    body = response.json()
    assert body["cpf_cnpj"] == "52998224725"
    assert body["phone"] == "+5521998765432"
    assert body["status"] == "ACTIVE"


def test_invalid_cpf_returns_field_error(as_a, api_client):
    response = _create(api_client, cpf_cnpj="529.982.247-24")
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"]["cpf_cnpj"] == ["CPF inválido."]


def test_company_accepts_alphanumeric_cnpj(as_a, api_client):
    response = _create(api_client, kind="PJ", name="Padaria Ltda", cpf_cnpj="12.ABC.345/01DE-35")
    assert response.status_code == 201
    assert response.json()["cpf_cnpj"] == "12ABC34501DE35"


def test_duplicate_document_in_same_tenant_is_rejected(as_a, api_client):
    assert _create(api_client).status_code == 201
    response = _create(api_client, name="Outra Maria")
    assert response.status_code == 400
    assert "Já existe" in response.json()["error"]["details"]["cpf_cnpj"][0]


def test_same_document_is_allowed_in_another_tenant(tenant_a, tenant_b, login, api_client):
    login(tenant_a.owner.email)
    assert _create(api_client).status_code == 201
    login(tenant_b.owner.email)
    assert _create(api_client).status_code == 201


def test_invalid_phone(as_a, api_client):
    response = _create(api_client, phone="9876-5432")
    assert response.status_code == 400
    assert "phone" in response.json()["error"]["details"]


def test_document_and_phone_are_optional(as_a, api_client):
    response = _create(api_client, cpf_cnpj="", phone="")
    assert response.status_code == 201


def test_search_by_name_document_and_phone(as_a, api_client):
    _create(api_client)
    _create(api_client, name="João Souza", cpf_cnpj="", phone="(21) 3456-7890")

    def names(q):
        return [c["name"] for c in api_client.get(URL, {"q": q}).json()["results"]]

    assert names("maria") == ["Maria da Silva"]
    assert names("529.982") == ["Maria da Silva"]
    assert names("3456-7890") == ["João Souza"]


def test_filter_by_status_and_reject_unknown_status(as_a, api_client):
    _create(api_client, status="LEAD", cpf_cnpj="")
    _create(api_client, name="Ativo", cpf_cnpj="")
    leads = api_client.get(URL, {"status": "LEAD"}).json()["results"]
    assert [c["status"] for c in leads] == ["LEAD"]
    assert api_client.get(URL, {"status": "XYZ"}).status_code == 400


def test_update_and_archive(as_a, api_client):
    client_id = _create(api_client).json()["id"]
    response = api_client.patch(f"{URL}{client_id}/", {"status": "ARCHIVED"}, format="json")
    assert response.status_code == 200
    assert response.json()["status"] == "ARCHIVED"


def test_changing_kind_revalidates_document(as_a, api_client):
    client_id = _create(api_client).json()["id"]
    response = api_client.patch(f"{URL}{client_id}/", {"kind": "PJ"}, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["details"]["cpf_cnpj"] == ["CNPJ inválido."]


def test_delete_sends_to_trash(as_a, api_client):
    client_id = _create(api_client).json()["id"]
    assert api_client.delete(f"{URL}{client_id}/").status_code == 204
    assert api_client.get(f"{URL}{client_id}/").status_code == 404


def test_other_tenant_cannot_see_or_edit_client(tenant_a, tenant_b, login, api_client):
    login(tenant_a.owner.email)
    client_id = _create(api_client).json()["id"]

    login(tenant_b.owner.email)
    assert api_client.get(f"{URL}{client_id}/").status_code == 404
    assert api_client.patch(f"{URL}{client_id}/", {"name": "x"}, format="json").status_code == 404
    assert api_client.get(URL).json()["count"] == 0


# ------------------------------------------------------------------ termo de ciência


def test_register_term_acceptance_uses_active_version(as_a, api_client):
    client_id = _create(api_client).json()["id"]
    url = f"{URL}{client_id}/term-acceptances/"

    response = api_client.post(url, {"channel": "IN_PERSON", "evidence": "pasta 12"}, format="json")
    assert response.status_code == 201
    assert response.json()["term_version"] == 1
    assert response.json()["recorded_by_name"] == as_a.owner.email

    with tenant_context(as_a.tenant.id):
        publish_term_version(body="Novo texto")
    api_client.post(url, {"channel": "WHATSAPP"}, format="json")

    versions = [a["term_version"] for a in api_client.get(url).json()]
    assert versions == [2, 1]


def test_term_acceptance_is_immutable(as_a, api_client):
    client_id = _create(api_client).json()["id"]
    api_client.post(f"{URL}{client_id}/term-acceptances/", {"channel": "EMAIL"}, format="json")
    with tenant_context(as_a.tenant.id):
        acceptance = ClientTermAcceptance.objects.get()
        acceptance.evidence = "alterado"
        with pytest.raises(ValueError, match="imutável"):
            acceptance.save()


def test_client_model_is_tenant_scoped(tenant_a, tenant_b):
    with tenant_context(tenant_a.tenant.id):
        Client.objects.create(name="Só do A")
    with tenant_context(tenant_b.tenant.id):
        assert Client.objects.count() == 0

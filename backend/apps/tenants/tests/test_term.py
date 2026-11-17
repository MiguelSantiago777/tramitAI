import pytest

from apps.accounts.models import Membership, User

pytestmark = pytest.mark.django_db

URL = "/api/v1/tenant/term/"


def test_new_tenant_gets_default_term_with_its_name(tenant_a, login, api_client):
    login(tenant_a.owner.email)
    body = api_client.get(URL).json()
    assert body["version"] == 1
    assert body["is_active"] is True
    assert "Escritorio A" in body["body"]
    assert "{{escritorio}}" not in body["body"]
    assert "inteligência artificial" in body["body"]


def test_owner_publishes_new_version_and_old_one_is_kept(tenant_a, login, api_client):
    login(tenant_a.owner.email)
    response = api_client.post(URL, {"body": "  Texto revisado.  "}, format="json")
    assert response.status_code == 201
    assert response.json()["version"] == 2
    assert response.json()["body"] == "Texto revisado."
    assert response.json()["created_by_name"] == tenant_a.owner.email

    versions = api_client.get(f"{URL}versions/").json()
    assert [(v["version"], v["is_active"]) for v in versions] == [(2, True), (1, False)]
    assert "Escritorio A" in versions[1]["body"]


def test_empty_body_is_rejected(tenant_a, login, api_client):
    login(tenant_a.owner.email)
    assert api_client.post(URL, {"body": "   "}, format="json").status_code == 400


def test_staff_cannot_publish_but_can_read(tenant_a, login, api_client):
    staff = User.objects.create_user(email="equipe@a.test", password="senha-de-teste-123")
    Membership.objects.create(user=staff, tenant=tenant_a.tenant, role=Membership.Role.STAFF)
    login("equipe@a.test")
    assert api_client.get(URL).status_code == 200
    response = api_client.post(URL, {"body": "x"}, format="json")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_terms_are_isolated_between_tenants(tenant_a, tenant_b, login, api_client):
    login(tenant_a.owner.email)
    api_client.post(URL, {"body": "Só do A"}, format="json")
    login(tenant_b.owner.email)
    assert [v["version"] for v in api_client.get(f"{URL}versions/").json()] == [1]


def test_members_lists_only_current_tenant(tenant_a, tenant_b, login, api_client):
    login(tenant_a.owner.email)
    members = api_client.get("/api/v1/tenant/members/").json()
    assert [m["email"] for m in members] == [tenant_a.owner.email]

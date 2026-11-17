import pytest

from apps.accounts.models import Membership
from apps.core.tenancy import tenant_context
from apps.tenants.models import Tenant, TenantSettings

pytestmark = pytest.mark.django_db


def test_login_with_single_tenant(tenant_a, login, api_client):
    response = login(tenant_a.owner.email)
    assert response.status_code == 200
    body = response.json()
    assert body["access"]
    assert body["refresh"]
    assert body["session"]["tenant"]["id"] == str(tenant_a.tenant.id)
    assert body["session"]["role"] == "OWNER"
    assert body["session"]["can_approve"] is True

    me = api_client.get("/api/v1/auth/me/")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == tenant_a.owner.email


def test_login_email_is_case_insensitive(tenant_a, login):
    assert login(tenant_a.owner.email.upper()).status_code == 200


def test_login_wrong_password(tenant_a, login):
    response = login(tenant_a.owner.email, password="errada")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_user_with_two_tenants_must_choose(make_tenant, login):
    first = make_tenant("Escritorio A", owner_email="dra@exemplo.test")
    second = make_tenant("Escritorio B", owner_email="dra@exemplo.test")

    response = login("dra@exemplo.test")
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "tenant_selection_required"
    assert {t["id"] for t in error["details"]["tenants"]} == {
        str(first.tenant.id),
        str(second.tenant.id),
    }

    response = login("dra@exemplo.test", tenant_id=second.tenant.id)
    assert response.status_code == 200
    assert response.json()["session"]["tenant"]["id"] == str(second.tenant.id)


def test_login_into_tenant_without_membership_is_forbidden(tenant_a, tenant_b, login):
    response = login(tenant_a.owner.email, tenant_id=tenant_b.tenant.id)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "tenant_forbidden"


def test_me_requires_token(api_client):
    response = api_client.get("/api/v1/auth/me/")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_token_stops_working_when_membership_is_revoked(tenant_a, login, api_client):
    login(tenant_a.owner.email)
    Membership.objects.filter(pk=tenant_a.membership.pk).update(is_active=False)

    response = api_client.get("/api/v1/auth/me/")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "tenant_forbidden"


def test_token_stops_working_when_tenant_is_suspended(tenant_a, login, api_client):
    login(tenant_a.owner.email)
    Tenant.objects.filter(pk=tenant_a.tenant.pk).update(status=Tenant.Status.SUSPENDED)
    assert api_client.get("/api/v1/auth/me/").status_code == 401


def test_refresh_keeps_tenant_claim(tenant_a, login, api_client):
    refresh = login(tenant_a.owner.email).json()["refresh"]
    response = api_client.post("/api/v1/auth/refresh/", {"refresh": refresh}, format="json")
    assert response.status_code == 200

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.json()['access']}")
    me = api_client.get("/api/v1/auth/me/")
    assert me.json()["tenant"]["id"] == str(tenant_a.tenant.id)


@pytest.mark.parametrize(("staff_can_approve", "expected"), [(False, False), (True, True)])
def test_staff_approval_follows_tenant_setting(
    tenant_a, login, api_client, staff_can_approve, expected
):
    from apps.accounts.models import User

    staff = User.objects.create_user(email="equipe@a.test", password="senha-de-teste-123")
    Membership.objects.create(user=staff, tenant=tenant_a.tenant, role=Membership.Role.STAFF)
    with tenant_context(tenant_a.tenant.id):
        TenantSettings.objects.update(staff_can_approve=staff_can_approve)

    response = login("equipe@a.test")
    assert response.json()["session"]["can_approve"] is expected

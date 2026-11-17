"""Isolamento entre escritórios pela API: cada token só enxerga o próprio tenant."""

import pytest

pytestmark = pytest.mark.django_db


def _settings_tenant(api_client):
    response = api_client.get("/api/v1/tenant/settings/")
    assert response.status_code == 200
    return response.json()["id"]


def _settings_id(created):
    from apps.core.tenancy import tenant_context
    from apps.tenants.models import TenantSettings

    with tenant_context(created.tenant.id):
        return str(TenantSettings.objects.get().id)


def test_each_tenant_sees_only_its_own_data(tenant_a, tenant_b, login, api_client):
    settings_a, settings_b = _settings_id(tenant_a), _settings_id(tenant_b)

    login(tenant_a.owner.email)
    assert _settings_tenant(api_client) == settings_a

    login(tenant_b.owner.email)
    assert _settings_tenant(api_client) == settings_b


def test_same_user_switches_tenant_only_through_token(make_tenant, login, api_client):
    first = make_tenant("Escritorio A", owner_email="dra@exemplo.test")
    second = make_tenant("Escritorio B", owner_email="dra@exemplo.test")

    login("dra@exemplo.test", tenant_id=first.tenant.id)
    assert _settings_tenant(api_client) == _settings_id(first)

    login("dra@exemplo.test", tenant_id=second.tenant.id)
    assert _settings_tenant(api_client) == _settings_id(second)


def test_tenant_context_does_not_leak_after_request(tenant_a, login, api_client):
    from apps.core.tenancy import peek_current_tenant_id

    login(tenant_a.owner.email)
    _settings_tenant(api_client)
    assert peek_current_tenant_id() is None

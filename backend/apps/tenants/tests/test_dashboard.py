from apps.processos.tests.fixtures import movement

URL = "/api/v1/tenant/dashboard/"


def test_dashboard_counts_only_current_tenant(
    tenant_a, tenant_b, account_a, monitored_case, sync, login, api_client
):
    sync(monitored_case)
    sync(monitored_case, movement("Conclusão"))

    login(tenant_a.owner.email)
    data = api_client.get(URL).json()
    assert data["pending_drafts"] == 1
    assert data["active_cases"] == 1
    assert data["cases_with_news"] == 1
    assert data["active_clients"] == 1
    assert [m["name"] for m in data["recent_movements"]] == ["Conclusão"]
    assert data["recent_movements"][0]["case_number"] == monitored_case.cnj_formatted

    api_client.credentials()
    login(tenant_b.owner.email)
    other = api_client.get(URL).json()
    assert other["pending_drafts"] == 0
    assert other["recent_movements"] == []

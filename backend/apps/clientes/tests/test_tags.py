from apps.clientes.models import Client, Tag
from apps.core.tenancy import tenant_context

TAGS = "/api/v1/tags/"
CLIENTS = "/api/v1/clients/"


def test_tag_crud_and_unique_name(tenant_a, login, api_client):
    login(tenant_a.owner.email)
    created = api_client.post(TAGS, {"name": "  Trabalhista ", "color": "green"}, format="json")
    assert created.status_code == 201
    assert created.json()["name"] == "Trabalhista"
    dup = api_client.post(TAGS, {"name": "trabalhista"}, format="json")
    assert dup.status_code == 400
    renamed = api_client.patch(f"{TAGS}{created.json()['id']}/", {"name": "CLT"}, format="json")
    assert renamed.json()["name"] == "CLT"


def test_client_tags_set_filter_and_delete(tenant_a, login, api_client):
    login(tenant_a.owner.email)
    vip = api_client.post(TAGS, {"name": "VIP"}, format="json").json()
    ind = api_client.post(TAGS, {"name": "Indicação", "color": "amber"}, format="json").json()
    ana = api_client.post(
        CLIENTS, {"name": "Ana", "tag_ids": [vip["id"], ind["id"]]}, format="json"
    ).json()
    assert {t["name"] for t in ana["tags"]} == {"VIP", "Indicação"}
    api_client.post(CLIENTS, {"name": "Bruno"}, format="json")

    only = api_client.patch(f"{CLIENTS}{ana['id']}/", {"tag_ids": [ind["id"]]}, format="json")
    assert [t["name"] for t in only.json()["tags"]] == ["Indicação"]
    untouched = api_client.patch(f"{CLIENTS}{ana['id']}/", {"notes": "x"}, format="json")
    assert [t["name"] for t in untouched.json()["tags"]] == ["Indicação"]

    filtered = api_client.get(f"{CLIENTS}?tag_id={ind['id']}").json()["results"]
    assert [c["name"] for c in filtered] == ["Ana"]
    counts = {t["name"]: t["client_count"] for t in api_client.get(TAGS).json()}
    assert counts == {"Indicação": 1, "VIP": 0}

    assert api_client.delete(f"{TAGS}{ind['id']}/").status_code == 204
    assert api_client.get(f"{CLIENTS}{ana['id']}/").json()["tags"] == []
    with tenant_context(tenant_a.tenant.id):
        assert Client.objects.filter(name="Ana").exists()  # apagar etiqueta não apaga cliente


def test_cannot_use_other_office_tag(tenant_a, tenant_b, login, api_client):
    with tenant_context(tenant_b.tenant.id):
        other = Tag.objects.create(name="Do B")
    login(tenant_a.owner.email)
    response = api_client.post(CLIENTS, {"name": "Ana", "tag_ids": [str(other.pk)]}, format="json")
    assert response.status_code == 400
    assert api_client.get(TAGS).json() == []

from datetime import timedelta

from django.utils import timezone

from apps.agenda.models import Event, Task
from apps.clientes.models import Client
from apps.core.tenancy import tenant_context
from apps.processos.models import LegalCase
from apps.processos.tests.fixtures import movement

URL = "/api/v1/clients/"


def _client_of(tenant_a, case: LegalCase) -> Client:
    with tenant_context(tenant_a.tenant.id):
        return Client.objects.get(case_links__case=case)


def test_timeline_brings_everything_about_the_client(
    tenant_a, account_a, monitored_case, sync, inbound, login, api_client
):
    sync(monitored_case)
    sync(monitored_case, movement("Conclusão"))
    maria = _client_of(tenant_a, monitored_case)
    inbound("Bom dia, alguma novidade?", wa_id="5521998765432")
    with tenant_context(tenant_a.tenant.id):
        task = Task.objects.create(title="Ligar para a Maria", client=maria)
        task.completed_at = timezone.now()
        task.status = Task.Status.DONE
        task.save()
        Event.objects.create(
            title="Reunião de alinhamento",
            client=maria,
            starts_at=timezone.now() + timedelta(days=2),
            location="Escritório",
        )
    login(tenant_a.owner.email)
    note = api_client.post(
        f"{URL}{maria.pk}/notes/",
        {
            "kind": "CALL",
            "body": "Liguei e expliquei a conclusão.",
            "legal_case_id": str(monitored_case.pk),
        },
        format="json",
    )
    assert note.status_code == 201
    assert note.json()["author_name"] == tenant_a.owner.email

    body = api_client.get(f"{URL}{maria.pk}/timeline/").json()
    types = [i["type"] for i in body["results"]]
    # Compromisso futuro aparece no topo; o resto do mais novo para o mais antigo.
    assert types[0] == "event"
    assert {"note", "task", "task_done", "message", "case", "movement"} <= set(types)
    by_type = {i["type"]: i for i in body["results"]}
    assert by_type["note"]["title"] == "Ligação"
    assert by_type["note"]["meta"]["case_number"] == monitored_case.cnj_formatted
    assert by_type["message"]["title"] == "Cliente escreveu"
    assert by_type["movement"]["meta"]["case_number"] == monitored_case.cnj_formatted
    stamps = [i["at"] for i in body["results"]]
    assert stamps == sorted(stamps, reverse=True)
    assert body["next_before"] is None


def test_timeline_pagination(tenant_a, login, api_client):
    with tenant_context(tenant_a.tenant.id):
        ana = Client.objects.create(name="Ana")
        for i in range(5):
            Task.objects.create(title=f"tarefa {i}", client=ana)
    login(tenant_a.owner.email)
    first = api_client.get(f"{URL}{ana.pk}/timeline/?limit=3").json()
    assert len(first["results"]) == 3
    assert first["next_before"]
    second = api_client.get(
        f"{URL}{ana.pk}/timeline/", {"limit": 3, "before": first["next_before"]}
    ).json()
    assert len(second["results"]) == 2
    assert second["next_before"] is None
    seen = {i["id"] for i in first["results"]} | {i["id"] for i in second["results"]}
    assert len(seen) == 5


def test_note_cannot_point_to_other_office_case(tenant_a, tenant_b, login, api_client):
    from apps.processos.tests.factories import make_cnj

    with tenant_context(tenant_b.tenant.id):
        other_case = LegalCase.objects.create(cnj_number=make_cnj(sequence=77))
    with tenant_context(tenant_a.tenant.id):
        ana = Client.objects.create(name="Ana")
    login(tenant_a.owner.email)
    response = api_client.post(
        f"{URL}{ana.pk}/notes/", {"body": "x", "legal_case_id": str(other_case.pk)}, format="json"
    )
    assert response.status_code == 400


def test_other_office_cannot_read_timeline(tenant_a, tenant_b, login, api_client):
    with tenant_context(tenant_a.tenant.id):
        ana = Client.objects.create(name="Ana")
    login(tenant_b.owner.email)
    assert api_client.get(f"{URL}{ana.pk}/timeline/").status_code == 404
    assert api_client.post(f"{URL}{ana.pk}/notes/", {"body": "x"}, format="json").status_code == 404

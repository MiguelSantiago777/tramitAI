from datetime import datetime, time, timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import Membership, User
from apps.agenda import services
from apps.agenda.models import Event, Task
from apps.aprovacoes.models import OutboundDraft
from apps.clientes.models import Client
from apps.core.models import AuditEvent
from apps.core.tenancy import tenant_context
from apps.processos.models import LegalCase
from apps.processos.tests.fixtures import movement

TASKS = "/api/v1/tasks/"
EVENTS = "/api/v1/events/"
DESK = "/api/v1/my-desk/"


@pytest.fixture
def maria(tenant_a):
    with tenant_context(tenant_a.tenant.id):
        return Client.objects.create(name="Maria da Silva", phone_e164="+5521998765432")


@pytest.fixture
def lawyer(tenant_a):
    user = User.objects.create_user(email="adv@a.test", password="senha-de-teste-123")
    Membership.objects.create(user=user, tenant=tenant_a.tenant, role=Membership.Role.LAWYER)
    return user


def _task(tenant, **fields):
    with tenant_context(tenant.tenant.id):
        return Task.objects.create(**fields)


# --------------------------------------------------------------------------- tarefas


def test_create_task_linked_to_client_and_assignee(tenant_a, maria, lawyer, login, api_client):
    login(tenant_a.owner.email)
    response = api_client.post(
        TASKS,
        {
            "title": "Pedir comprovante de residência",
            "kind": "FOLLOW_UP",
            "due_date": str(services.today()),
            "assignee_id": str(lawyer.pk),
            "client_id": str(maria.pk),
        },
        format="json",
    )
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["assignee_name"] == "adv@a.test"
    assert body["client_name"] == "Maria da Silva"
    assert body["status"] == "OPEN"


def test_cannot_link_client_or_member_of_other_office(tenant_a, tenant_b, login, api_client):
    with tenant_context(tenant_b.tenant.id):
        other_client = Client.objects.create(name="Cliente do B")
    login(tenant_a.owner.email)
    response = api_client.post(
        TASKS,
        {
            "title": "x",
            "client_id": str(other_client.pk),
            "assignee_id": str(tenant_b.owner.pk),
        },
        format="json",
    )
    assert response.status_code == 400
    assert set(response.json()["error"]["details"]) == {"client_id", "assignee_id"}


def test_complete_and_reopen(tenant_a, login, api_client):
    task = _task(tenant_a, title="Protocolar petição")
    login(tenant_a.owner.email)
    done = api_client.post(f"{TASKS}{task.pk}/complete/").json()
    assert done["status"] == "DONE"
    assert done["completed_by_name"] == tenant_a.owner.email
    assert done["completed_at"]
    reopened = api_client.post(f"{TASKS}{task.pk}/reopen/").json()
    assert (reopened["status"], reopened["completed_at"]) == ("OPEN", None)
    # Concluir só pela ação (para registrar quem e quando).
    patch = api_client.patch(f"{TASKS}{task.pk}/", {"status": "DONE"}, format="json")
    assert patch.status_code == 400


def test_list_filters(tenant_a, lawyer, maria, login, api_client):
    day = services.today()
    _task(
        tenant_a, title="atrasada minha", due_date=day - timedelta(days=2), assignee=tenant_a.owner
    )
    _task(tenant_a, title="hoje do advogado", due_date=day, assignee=lawyer)
    _task(tenant_a, title="sem data da maria", client=maria)
    login(tenant_a.owner.email)

    def titles(query: str) -> set[str]:
        return {t["title"] for t in api_client.get(f"{TASKS}?{query}").json()["results"]}

    assert titles("assignee=me") == {"atrasada minha"}
    assert titles("due=overdue") == {"atrasada minha"}
    assert titles("due=today") == {"hoje do advogado"}
    assert titles("due=none") == {"sem data da maria"}
    assert titles(f"client_id={maria.pk}") == {"sem data da maria"}
    assert titles("q=advogado") == {"hoje do advogado"}


def test_other_office_never_sees_tasks(tenant_a, tenant_b, login, api_client):
    task = _task(tenant_a, title="segredo do A")
    login(tenant_b.owner.email)
    assert api_client.get(TASKS).json()["count"] == 0
    assert api_client.get(f"{TASKS}{task.pk}/").status_code == 404


def test_my_desk_groups_mine_and_unassigned(tenant_a, lawyer, login, api_client):
    day = services.today()
    _task(tenant_a, title="atrasada", due_date=day - timedelta(days=1), assignee=tenant_a.owner)
    _task(tenant_a, title="hoje sem dono", due_date=day)
    _task(
        tenant_a, title="semana que vem", due_date=day + timedelta(days=3), assignee=tenant_a.owner
    )
    _task(tenant_a, title="do advogado", due_date=day, assignee=lawyer)
    _task(tenant_a, title="feita", due_date=day, status=Task.Status.DONE, assignee=tenant_a.owner)
    tz = services.TZ
    with tenant_context(tenant_a.tenant.id):
        Event.objects.create(
            title="Audiência Maria",
            kind=Event.Kind.HEARING,
            starts_at=datetime.combine(day, time(23, 0), tzinfo=tz),
        )
        Event.objects.create(
            title="Reunião",
            starts_at=datetime.combine(day + timedelta(days=2), time(10, 0), tzinfo=tz),
            responsible=tenant_a.owner,
        )
    login(tenant_a.owner.email)
    desk = api_client.get(DESK).json()
    assert [t["title"] for t in desk["overdue"]] == ["atrasada"]
    assert [t["title"] for t in desk["today"]] == ["hoje sem dono"]
    assert [t["title"] for t in desk["upcoming"]] == ["semana que vem"]
    assert [e["title"] for e in desk["events_today"]] == ["Audiência Maria"]
    assert [e["title"] for e in desk["events_upcoming"]] == ["Reunião"]


# --------------------------------------------------------------------------- andamentos → tarefas


@pytest.fixture
def case_with_owner(tenant_a, monitored_case, sync):
    with tenant_context(tenant_a.tenant.id):
        LegalCase.objects.filter(pk=monitored_case.pk).update(responsible=tenant_a.owner)
    sync(monitored_case)  # linha de base
    return monitored_case


def _tasks(tenant_a):
    with tenant_context(tenant_a.tenant.id):
        return list(Task.objects.select_related("assignee", "client").order_by("created_at"))


def test_intimation_creates_verify_deadline_task_without_inventing_date(
    tenant_a, case_with_owner, sync
):
    sync(case_with_owner, movement("Expedição de documento", complements=("tipo: Intimação",)))
    [task] = _tasks(tenant_a)
    assert task.kind == Task.Kind.DEADLINE
    assert task.title.startswith("Verificar prazo:")
    assert task.priority == Task.Priority.HIGH
    assert task.due_date == services.today()  # data para VERIFICAR, não o prazo
    assert "não calcula prazos" in task.description
    assert task.assignee == tenant_a.owner
    assert task.client is not None
    assert task.client.name == "Maria da Silva"

    sync(case_with_owner)  # nova consulta, mesmo andamento: não duplica
    assert len(_tasks(tenant_a)) == 1


def test_hearing_and_sentence_create_tasks_routine_does_not(tenant_a, case_with_owner, sync):
    sync(
        case_with_owner,
        movement("Juntada de Petição"),
        movement("Audiência de conciliação designada"),
        movement("Julgado procedente o pedido"),
    )
    titles = sorted(t.title for t in _tasks(tenant_a))
    assert titles == [
        "Analisar: Julgado procedente o pedido",
        "Conferir audiência: Audiência de conciliação designada",
    ]


def test_baseline_history_creates_no_tasks(tenant_a, monitored_case, fake_source, sync):
    from dataclasses import replace

    snap = fake_source.snapshots[monitored_case.cnj_number]
    fake_source.snapshots[monitored_case.cnj_number] = replace(
        snap, movements=(*snap.movements, movement("Intimação eletrônica"))
    )
    sync(monitored_case)
    assert _tasks(tenant_a) == []


# --------------------------------------------------------------------------- agenda


def test_event_validation(tenant_a, login, api_client):
    login(tenant_a.owner.email)
    start = timezone.now() + timedelta(days=1)
    bad = api_client.post(
        EVENTS,
        {
            "title": "x",
            "starts_at": start.isoformat(),
            "ends_at": (start - timedelta(hours=1)).isoformat(),
        },
        format="json",
    )
    assert "ends_at" in bad.json()["error"]["details"]
    no_client = api_client.post(
        EVENTS,
        {"title": "x", "starts_at": start.isoformat(), "remind_client": True},
        format="json",
    )
    assert "remind_client" in no_client.json()["error"]["details"]


def test_event_list_by_week_excludes_canceled(tenant_a, login, api_client):
    tz = services.TZ
    monday = services.today()
    with tenant_context(tenant_a.tenant.id):
        Event.objects.create(title="dentro", starts_at=datetime.combine(monday, time(9), tzinfo=tz))
        Event.objects.create(
            title="fora", starts_at=datetime.combine(monday + timedelta(days=9), time(9), tzinfo=tz)
        )
        Event.objects.create(
            title="cancelado",
            starts_at=datetime.combine(monday, time(10), tzinfo=tz),
            status=Event.Status.CANCELED,
        )
    login(tenant_a.owner.email)
    end = monday + timedelta(days=6)
    body = api_client.get(f"{EVENTS}?start={monday}&end={end}").json()
    assert [e["title"] for e in body["results"]] == ["dentro"]


def test_reminder_becomes_draft_once_and_reschedule_rearms(
    tenant_a, account_a, maria, drafts, login, api_client
):
    start = timezone.now() + timedelta(hours=24)
    login(tenant_a.owner.email)
    event = api_client.post(
        EVENTS,
        {
            "title": "Audiência de conciliação",
            "kind": "HEARING",
            "starts_at": start.isoformat(),
            "location": "Fórum de Nova Iguaçu, sala 3",
            "client_id": str(maria.pk),
            "remind_client": True,
        },
        format="json",
    ).json()

    assert services.create_event_reminders() == 1
    assert services.create_event_reminders() == 0  # não duplica
    [draft] = drafts(origin=OutboundDraft.Origin.EVENT_REMINDER)
    assert draft.status == OutboundDraft.Status.DRAFT  # nada sai sem aprovação
    assert draft.generated_body.startswith("Olá, Maria! Passando para lembrar: sua audiência")
    assert "Fórum de Nova Iguaçu, sala 3" in draft.generated_body

    new_start = start + timedelta(hours=2)
    api_client.patch(f"{EVENTS}{event['id']}/", {"starts_at": new_start.isoformat()}, format="json")
    assert services.create_event_reminders() == 1


def test_reminder_without_whatsapp_is_skipped_and_audited(tenant_a, maria, login, api_client):
    with tenant_context(tenant_a.tenant.id):
        Client.objects.filter(pk=maria.pk).update(phone_e164="")
        Event.objects.create(
            title="Reunião",
            starts_at=timezone.now() + timedelta(hours=20),
            client=maria,
            remind_client=True,
        )
    assert services.create_event_reminders() == 0
    with tenant_context(tenant_a.tenant.id):
        assert AuditEvent.objects.filter(action="event.reminder_skipped").count() == 1


def test_reminder_text_hours():
    tz = services.TZ
    event = Event(
        title="x",
        kind=Event.Kind.CONSULTATION,
        starts_at=datetime(2026, 11, 18, 14, 30, tzinfo=tz),
    )
    assert services.reminder_text(event, "Ana") == (
        "Olá, Ana! Passando para lembrar: seu atendimento está marcado para 18/11 às 14h30. "
        "Qualquer dúvida, é só responder esta mensagem."
    )
    event.starts_at = datetime(2026, 11, 18, 9, 0, tzinfo=tz)
    assert "às 09h." in services.reminder_text(event, "")

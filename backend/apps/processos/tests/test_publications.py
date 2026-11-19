"""Publicações do Diário (DJEN) por OAB: parsing, busca, dedupe, tarefas, API e plano."""

import json
from datetime import date, timedelta
from typing import Any

import httpx
import pytest
from django.utils import timezone

from apps.agenda.models import Task
from apps.cobranca.models import Plan, Subscription
from apps.core.tenancy import tenant_context
from apps.processos import publications
from apps.processos.cnj import format_cnj
from apps.processos.models import LegalCase, MonitoredOab, Publication
from apps.processos.sources import SourceError, get_publication_source
from apps.processos.sources.djen import (
    Communication,
    DjenSource,
    FakeDjenSource,
    deadline_hints,
    html_to_text,
    parse_item,
)

from .factories import make_cnj

pytestmark = pytest.mark.django_db

OABS = "/api/v1/monitored-oabs/"
PUBS = "/api/v1/publications/"

HTML = (
    "<html><head><style>p{}</style></head><body><article>"
    "<section><b>EXECU&Ccedil;&Atilde;O N&ordm; 4000346-85.2026.8.26.0222/SP</b></section>"
    "<section><table><tr><td>EXEQUENTE</td><td>: BANCO X</td></tr></table></section>"
    "<p>Intime-se o autor para que, no prazo de 15 (quinze) dias, manifeste-se.</p>"
    "<script>alert(1)</script></article></body></html>"
)


def comm(djen_id: int, cnj: str = "", *, day: date | None = None, **extra: Any) -> Communication:
    values: dict[str, Any] = {
        "djen_id": djen_id,
        "cnj_number": cnj,
        "tribunal": "TJRJ",
        "kind": "Intimação",
        "document_type": "Despacho",
        "orgao": "1ª Vara Cível",
        "classe": "PROCEDIMENTO COMUM CíVEL",
        "available_on": day or timezone.localdate(),
        "text": "Manifeste-se no prazo de 5 dias úteis.",
        "link": "https://tj.example/doc",
    }
    values.update(extra)
    return Communication(**values)


@pytest.fixture
def djen() -> FakeDjenSource:
    source = get_publication_source()
    assert isinstance(source, FakeDjenSource)
    source.items.clear()
    source.calls.clear()
    source.fail_next = None
    return source


@pytest.fixture
def oab(tenant_a: Any) -> MonitoredOab:
    with tenant_context(tenant_a.tenant.id):
        return MonitoredOab.objects.create(
            number="123456", uf="RJ", lawyer_name="Dra. Ana", user=tenant_a.owner
        )


def _sync(tenant: Any, oab: MonitoredOab, django_capture_on_commit_callbacks: Any) -> str:
    with django_capture_on_commit_callbacks(execute=True):
        return publications.sync_oab(tenant.tenant.id, oab.pk)


# ------------------------------------------------------------------------------- parsing


def test_html_to_text_strips_tags_scripts_and_entities():
    text = html_to_text(HTML)
    assert "<" not in text
    assert "alert" not in text
    assert "EXECUÇÃO Nº 4000346-85.2026.8.26.0222/SP" in text
    assert "EXEQUENTE : BANCO X" in text
    assert "prazo de 15 (quinze) dias" in text


def test_deadline_hints_only_quotes_the_text():
    assert deadline_hints("no prazo de 15 (quinze) dias, e prazo comum de 5 dias úteis") == [
        "15 dias",
        "5 dias úteis",
    ]
    assert deadline_hints("prazo de 48 horas") == ["48 horas"]
    assert deadline_hints("sem prazo aqui") == []


def test_parse_item_real_shape_and_cancelled():
    raw = {
        "id": 791694546,
        "data_disponibilizacao": "2026-11-19",
        "siglaTribunal": "TJSP",
        "tipoComunicacao": "Intimação",
        "nomeOrgao": "Central de Mandados - Porto Feliz",
        "numero_processo": "40008817220268260526",
        "link": "https://eproc1g.tjsp.jus.br/doc",
        "tipoDocumento": "Ato ordinatório",
        "nomeClasse": "PROCEDIMENTO COMUM CíVEL",
        "ativo": True,
        "texto": HTML,
        "destinatarios": [{"nome": "BANCO SANTANDER (BRASIL) S.A.", "polo": "A"}],
    }
    item = parse_item(raw)
    assert item is not None
    assert item.djen_id == 791694546
    assert item.cnj_number == "40008817220268260526"
    assert item.available_on == date(2026, 11, 19)
    assert item.recipients == ("BANCO SANTANDER (BRASIL) S.A.",)
    assert "<" not in item.text
    assert parse_item({**raw, "ativo": False}) is None
    assert parse_item({**raw, "link": "javascript:alert(1)"}).link == ""  # type: ignore[union-attr]
    assert parse_item({"id": "x"}) is None


def test_djen_source_paginates_and_maps_errors():
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        seen.append(params)
        page = int(params["pagina"])
        base = {"id": 0, "data_disponibilizacao": "2026-11-19", "numero_processo": ""}
        count = 150
        size = 100 if page == 1 else 50
        items = [{**base, "id": page * 1000 + i} for i in range(size)]
        return httpx.Response(200, json={"status": "success", "count": count, "items": items})

    source = DjenSource(httpx.Client(transport=httpx.MockTransport(handler)))
    found = source.fetch("123456", "RJ", date(2026, 11, 12), date(2026, 11, 19))
    assert len(found) == 150
    assert [p["pagina"] for p in seen] == ["1", "2"]
    assert seen[0]["numeroOab"] == "123456"
    assert seen[0]["ufOab"] == "RJ"
    assert seen[0]["dataDisponibilizacaoInicio"] == "2026-11-12"

    limited = DjenSource(httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429))))
    with pytest.raises(SourceError) as exc:
        limited.fetch("1", "RJ", date(2026, 11, 1), date(2026, 11, 2))
    assert exc.value.code == "http_429"
    assert exc.value.retryable is True

    broken = DjenSource(
        httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html>")))
    )
    with pytest.raises(SourceError) as exc:
        broken.fetch("1", "RJ", date(2026, 11, 1), date(2026, 11, 2))
    assert exc.value.code == "bad_response"


# ------------------------------------------------------------------------------- sync


def test_sync_creates_links_case_and_tasks_and_is_idempotent(
    tenant_a, oab, djen, django_capture_on_commit_callbacks
):
    cnj = make_cnj()
    with tenant_context(tenant_a.tenant.id):
        case = LegalCase.objects.create(cnj_number=cnj, responsible=tenant_a.owner)
    djen.items[("123456", "RJ")] = [
        comm(1, cnj),
        comm(2, "", kind="Edital", text="Edital de leilão."),
        comm(3, cnj, day=timezone.localdate() - timedelta(days=20)),  # fora da janela inicial
    ]

    assert _sync(tenant_a, oab, django_capture_on_commit_callbacks) == "new:2"
    _, _, start, end = djen.calls[-1]
    assert end == timezone.localdate()
    assert start == end - timedelta(days=7)

    with tenant_context(tenant_a.tenant.id):
        pubs = {p.djen_id: p for p in Publication.objects.all()}
        assert set(pubs) == {1, 2}
        assert pubs[1].legal_case_id == case.pk
        assert pubs[1].deadline_hints == ["5 dias úteis"]
        assert pubs[2].legal_case_id is None

        tasks = {t.source_publication_id: t for t in Task.objects.all()}
        deadline = tasks[pubs[1].pk]
        assert deadline.kind == Task.Kind.DEADLINE
        assert deadline.title == f"Verificar prazo: Intimação — {format_cnj(cnj)}"
        assert deadline.legal_case_id == case.pk
        assert deadline.assignee_id == tenant_a.owner.pk
        assert "5 dias úteis" in deadline.description
        assert "não calcula prazos" in deadline.description
        assert tasks[pubs[2].pk].kind == Task.Kind.TASK
        assert tasks[pubs[2].pk].title == "Ler publicação: Edital — sem número"

        oab.refresh_from_db()
        assert oab.fetched_until == timezone.localdate()

    # Rodar de novo não duplica nada e recomeça 1 dia antes do último sucesso.
    assert _sync(tenant_a, oab, django_capture_on_commit_callbacks) == "unchanged"
    _, _, start, _ = djen.calls[-1]
    assert start == timezone.localdate() - timedelta(days=1)
    with tenant_context(tenant_a.tenant.id):
        assert Publication.objects.count() == 2
        assert Task.objects.count() == 2


def test_same_publication_for_two_oabs_is_stored_once(
    tenant_a, oab, djen, django_capture_on_commit_callbacks
):
    with tenant_context(tenant_a.tenant.id):
        other = MonitoredOab.objects.create(number="999", uf="RJ")
    djen.items[("123456", "RJ")] = [comm(7)]
    djen.items[("999", "RJ")] = [comm(7)]
    _sync(tenant_a, oab, django_capture_on_commit_callbacks)
    assert _sync(tenant_a, other, django_capture_on_commit_callbacks) == "unchanged"
    with tenant_context(tenant_a.tenant.id):
        assert Publication.objects.count() == 1
        assert Task.objects.count() == 1


def test_source_errors(tenant_a, oab, djen, django_capture_on_commit_callbacks):
    djen.fail_next = SourceError("http_429", retryable=True)
    with pytest.raises(publications.RetryableSyncError):
        _sync(tenant_a, oab, django_capture_on_commit_callbacks)
    djen.fail_next = SourceError("http_400", retryable=False)
    assert _sync(tenant_a, oab, django_capture_on_commit_callbacks) == "error:http_400"
    with tenant_context(tenant_a.tenant.id):
        oab.refresh_from_db()
        assert oab.last_error == "http_400"
        assert oab.fetched_until is None


def test_publications_are_isolated_per_tenant(
    tenant_a, tenant_b, oab, djen, django_capture_on_commit_callbacks
):
    djen.items[("123456", "RJ")] = [comm(1)]
    _sync(tenant_a, oab, django_capture_on_commit_callbacks)
    with tenant_context(tenant_b.tenant.id):
        assert Publication.objects.count() == 0
        assert Publication.unscoped.count() == 0  # RLS


def test_schedule_skips_plans_without_the_feature(tenant_a, tenant_b, oab, djen):
    with tenant_context(tenant_b.tenant.id):
        MonitoredOab.objects.create(number="1", uf="SP")
    Subscription.objects.create(
        tenant=tenant_b.tenant,
        plan=Plan.objects.get(code="essencial"),
        status=Subscription.Status.ACTIVE,
    )
    assert publications.schedule_due_checks() == 1
    assert [c[:2] for c in djen.calls] == [("123456", "RJ")]


# ------------------------------------------------------------------------------- API


@pytest.fixture
def as_a(tenant_a, login):
    login(tenant_a.owner.email)
    return tenant_a


def test_create_oab_runs_first_search_now(
    as_a, api_client, djen, django_capture_on_commit_callbacks
):
    djen.items[("123456", "SP")] = [comm(1)]
    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.post(
            OABS, {"number": "SP 123.456", "uf": "sp", "lawyer_name": "Dra. Ana"}, format="json"
        )
    assert response.status_code == 201, response.json()
    assert response.json()["number"] == "123456"
    assert response.json()["uf"] == "SP"
    assert response.json()["user_id"] == str(as_a.owner.pk)

    listed = api_client.get(OABS).json()["results"]
    assert listed[0]["new_count"] == 1
    assert listed[0]["fetched_until"] == timezone.localdate().isoformat()

    dup = api_client.post(OABS, {"number": "123456", "uf": "SP"}, format="json")
    assert dup.status_code == 400
    assert dup.json()["error"]["details"]["number"] == ["Esta OAB já está cadastrada."]
    bad = api_client.post(OABS, {"number": "abc", "uf": "XX"}, format="json")
    assert set(bad.json()["error"]["details"]) == {"number", "uf"}


def test_check_now_has_cooldown(as_a, api_client, oab, djen, django_capture_on_commit_callbacks):
    url = f"{OABS}{oab.pk}/check/"
    with django_capture_on_commit_callbacks(execute=True):
        assert api_client.post(url).status_code == 202
    assert len(djen.calls) == 1
    response = api_client.post(url)
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "checked_recently"


def test_list_mark_and_create_case(as_a, api_client, oab, djen, django_capture_on_commit_callbacks):
    cnj = make_cnj()
    djen.items[("123456", "RJ")] = [comm(1, cnj), comm(2, "")]
    _sync(as_a, oab, django_capture_on_commit_callbacks)

    body = api_client.get(PUBS, {"status": "NEW"}).json()
    assert body["count"] == 2
    item = next(p for p in body["results"] if p["djen_id"] == 1)
    assert item["cnj_formatted"] == format_cnj(cnj)
    assert item["case_id"] is None
    assert item["oab_label"] == "OAB 123456/RJ · Dra. Ana"
    assert api_client.get(PUBS + "summary/").json() == {"new": 2}
    assert api_client.get(PUBS, {"q": cnj[:7]}).json()["count"] == 1

    created = api_client.post(f"{PUBS}{item['id']}/create-case/")
    assert created.status_code == 200
    case_id = created.json()["case_id"]
    case = api_client.get(f"/api/v1/cases/{case_id}/").json()
    assert case["cnj_number"] == cnj
    assert case["classe"] == "Procedimento comum cível"
    assert case["responsible_id"] == str(as_a.owner.pk)
    # Segunda vez devolve o mesmo processo; a publicação e a tarefa ficam amarradas.
    assert api_client.post(f"{PUBS}{item['id']}/create-case/").json()["case_id"] == case_id
    assert api_client.get(PUBS, {"case_id": case_id}).json()["count"] == 1
    with tenant_context(as_a.tenant.id):
        assert Task.objects.get(source_publication_id=item["id"]).legal_case_id is not None

    no_cnj = next(p for p in body["results"] if p["djen_id"] == 2)
    assert api_client.post(f"{PUBS}{no_cnj['id']}/create-case/").status_code == 400

    marked = api_client.post(f"{PUBS}{item['id']}/mark/", {"status": "DONE"}, format="json")
    assert marked.json()["status"] == "DONE"
    assert marked.json()["handled_by_name"]
    assert api_client.get(PUBS + "summary/").json() == {"new": 1}
    reopened = api_client.post(f"{PUBS}{item['id']}/mark/", {"status": "NEW"}, format="json")
    assert reopened.json()["handled_by_name"] == ""


def test_case_created_by_hand_picks_up_old_publications(
    as_a, api_client, oab, djen, django_capture_on_commit_callbacks
):
    cnj = make_cnj(sequence=801999)
    djen.items[("123456", "RJ")] = [comm(1, cnj)]
    _sync(as_a, oab, django_capture_on_commit_callbacks)
    response = api_client.post("/api/v1/cases/", {"cnj_number": cnj}, format="json")
    assert response.status_code == 201
    assert api_client.get(PUBS, {"case_id": response.json()["id"]}).json()["count"] == 1


def test_other_tenant_cannot_see_or_touch(tenant_b, login, api_client, oab, djen, as_a):
    djen.items[("123456", "RJ")] = [comm(1)]
    publications.sync_oab(as_a.tenant.id, oab.pk)
    pub_id = api_client.get(PUBS).json()["results"][0]["id"]
    login(tenant_b.owner.email)
    assert api_client.get(PUBS).json()["count"] == 0
    assert api_client.get(f"{PUBS}{pub_id}/").status_code == 404
    assert (
        api_client.post(f"{PUBS}{pub_id}/mark/", {"status": "DONE"}, format="json").status_code
        == 404
    )
    assert api_client.delete(f"{OABS}{oab.pk}/").status_code == 404


def test_plan_without_feature_gets_402(tenant_a, login, api_client):
    Subscription.objects.create(
        tenant=tenant_a.tenant,
        plan=Plan.objects.get(code="essencial"),
        status=Subscription.Status.TRIAL,
        trial_ends_at=timezone.now() + timedelta(days=10),
    )
    login(tenant_a.owner.email)
    response = api_client.get(PUBS)
    assert response.status_code == 402
    assert response.json()["error"]["code"] == "plan_feature"
    assert api_client.post(OABS, {"number": "1", "uf": "SP"}, format="json").status_code == 402


def test_paid_tiers_include_publications(db):
    flags = dict(
        Plan.objects.filter(code__in=["essencial", "escritorio", "equipe"]).values_list(
            "code", "includes_publications"
        )
    )
    assert flags == {"essencial": False, "escritorio": True, "equipe": True}


def test_json_roundtrip_of_hints_is_plain_list(
    tenant_a, oab, djen, django_capture_on_commit_callbacks
):
    djen.items[("123456", "RJ")] = [comm(1, text="prazo de 10 dias e prazo de 10 dias")]
    _sync(tenant_a, oab, django_capture_on_commit_callbacks)
    with tenant_context(tenant_a.tenant.id):
        assert json.loads(json.dumps(Publication.objects.get().deadline_hints)) == ["10 dias"]

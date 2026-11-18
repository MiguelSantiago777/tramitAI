"""Google Agenda: conectar, refletir compromissos e a Lia respeitar o ocupado do Google."""

from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.agenda import google, scheduling
from apps.agenda.models import Event, GoogleCalendarConnection
from apps.core.tenancy import tenant_atomic, tenant_context
from apps.tenants.models import TenantSettings

TZ = ZoneInfo("America/Sao_Paulo")
URL = "/api/v1/agenda/google/"
CALLBACK = "/api/oauth/google/callback/"


@pytest.fixture
def fake_google():
    client = google.get_google()
    assert isinstance(client, google.FakeGoogle)
    client.events.clear()
    client.busy_blocks.clear()
    client.revoked.clear()
    client.fail_next = None
    return client


def _connect(api_client, client, login, tenant_a, django_capture_on_commit_callbacks):
    login(tenant_a.owner.email)
    url = api_client.post(URL).json()["authorization_url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    with django_capture_on_commit_callbacks(execute=True):
        return client.get(CALLBACK, {"code": "abc", "state": state})


def test_connect_flow_stores_encrypted_token(
    tenant_a, login, api_client, client, fake_google, django_capture_on_commit_callbacks
):
    login(tenant_a.owner.email)
    assert api_client.get(URL).json()["connected"] is False
    url = api_client.post(URL).json()["authorization_url"]
    query = parse_qs(urlparse(url).query)
    assert "https://www.googleapis.com/auth/calendar.events" in query["scope"][0]
    assert query["access_type"] == ["offline"]
    assert query["redirect_uri"][0].endswith("/api/oauth/google/callback/")

    response = client.get(CALLBACK, {"code": "abc", "state": query["state"][0]})
    assert response.status_code == 302
    assert response["Location"].endswith("/agenda?google=conectado")
    status = api_client.get(URL).json()
    assert status["connected"] is True
    assert status["google_email"] == "advogada@gmail.com"
    with tenant_context(tenant_a.tenant.id):
        stored = GoogleCalendarConnection.objects.get().refresh_token_encrypted
    assert "refresh-abc" not in stored

    assert api_client.delete(URL).json()["connected"] is False
    assert fake_google.revoked == ["refresh-abc"]


def test_callback_rejects_forged_or_cancelled(client, fake_google):
    assert client.get(CALLBACK, {"code": "x", "state": "falso"})["Location"].endswith("expirado")
    assert client.get(CALLBACK, {"error": "access_denied"})["Location"].endswith("cancelado")


def test_event_goes_to_google_and_follows_changes(
    tenant_a, login, api_client, client, fake_google, django_capture_on_commit_callbacks
):
    _connect(api_client, client, login, tenant_a, django_capture_on_commit_callbacks)
    start = timezone.now() + timedelta(days=2)
    with django_capture_on_commit_callbacks(execute=True):
        created = api_client.post(
            "/api/v1/events/",
            {
                "title": "Audiência",
                "starts_at": start.isoformat(),
                "ends_at": (start + timedelta(hours=1)).isoformat(),
                "responsible_id": str(tenant_a.owner.pk),
            },
            format="json",
        ).json()
    [(google_id, body)] = fake_google.events.items()
    assert body["summary"] == "Audiência"
    assert body["status"] == "confirmed"

    with django_capture_on_commit_callbacks(execute=True):
        api_client.patch(f"/api/v1/events/{created['id']}/", {"title": "Audiência remarcada"})
    assert fake_google.events[google_id]["summary"] == "Audiência remarcada"
    assert len(fake_google.events) == 1  # atualizou, não duplicou

    with django_capture_on_commit_callbacks(execute=True):
        api_client.patch(f"/api/v1/events/{created['id']}/", {"status": "CANCELED"})
    assert fake_google.events == {}


def test_lia_prebook_goes_tentative(
    tenant_a, login, api_client, client, fake_google, django_capture_on_commit_callbacks
):
    _connect(api_client, client, login, tenant_a, django_capture_on_commit_callbacks)
    with django_capture_on_commit_callbacks(execute=True), tenant_atomic(tenant_a.tenant.id):
        Event.objects.create(
            title="Consulta inicial - João",
            status=Event.Status.PENDING,
            starts_at=timezone.now() + timedelta(days=1),
            responsible=tenant_a.owner,
        )
    [body] = fake_google.events.values()
    assert body["status"] == "tentative"
    assert body["summary"].startswith("[A confirmar]")


def test_lia_does_not_offer_google_busy_time(
    tenant_a, login, api_client, client, fake_google, django_capture_on_commit_callbacks
):
    monday_8h = datetime(2026, 11, 23, 8, 0, tzinfo=TZ)
    # Dentista marcado direto no Google, segunda das 10h às 12h.
    fake_google.busy_blocks.append(
        (datetime(2026, 11, 23, 10, 0, tzinfo=TZ), datetime(2026, 11, 23, 12, 0, tzinfo=TZ))
    )
    with tenant_atomic(tenant_a.tenant.id):
        TenantSettings.objects.update(scheduling_enabled=True)
    _connect(api_client, client, login, tenant_a, django_capture_on_commit_callbacks)
    with tenant_atomic(tenant_a.tenant.id):
        cfg = TenantSettings.objects.get()
        GoogleCalendarConnection.objects.update(
            busy_cache=[[s.isoformat(), e.isoformat()] for s, e in fake_google.busy_blocks]
        )
        slots = scheduling.free_slots(cfg, now=monday_8h)
    labels = [s.astimezone(TZ).strftime("%a %H:%M") for s in slots]
    assert "Mon 10:00" not in labels
    assert "Mon 11:00" not in labels
    assert labels[0] == "Mon 13:00"


def test_expired_authorization_asks_to_reconnect(
    tenant_a, login, api_client, client, fake_google, django_capture_on_commit_callbacks
):
    _connect(api_client, client, login, tenant_a, django_capture_on_commit_callbacks)
    with tenant_context(tenant_a.tenant.id):
        conn = GoogleCalendarConnection.objects.get()
    fake_google.fail_next = google.GoogleError("reconnect")
    with pytest.raises(google.GoogleError):
        google.refresh_busy(tenant_a.tenant.id, conn.pk)
    assert api_client.get(URL).json()["needs_reconnect"] is True

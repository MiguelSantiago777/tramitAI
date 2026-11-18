"""Integração com o Google Agenda de cada advogado.

- TramitAI → Google: compromisso criado, alterado ou cancelado aqui é refletido no Google
  (pré-reserva da Lia entra como "provisório").
- Google → Lia: só livre/ocupado (freeBusy), guardado em cache, para a Lia não oferecer
  horário que bate com compromisso marcado direto no Google. Título e detalhes dos eventos do
  Google nunca são lidos.

Regras: HTTP nunca dentro de transação aberta; token de atualização guardado cifrado; nada de
conteúdo em log.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import cache
from typing import Any, Protocol
from urllib.parse import quote, urlencode

import httpx
from django.conf import settings
from django.core import signing
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.accounts.models import User
from apps.core.crypto import decrypt_secret, encrypt_secret
from apps.core.tenancy import tenant_atomic

from .models import Event, GoogleCalendarConnection

logger = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
SCOPES = [
    "openid",
    "email",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.freebusy",
]
STATE_SALT = "tramitai.google-calendar"
STATE_MAX_AGE = 15 * 60
BUSY_DAYS = 15
BUSY_STALE = timedelta(minutes=5)
TZ_NAME = "America/Sao_Paulo"


class GoogleError(Exception):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class Tokens:
    access_token: str
    refresh_token: str
    email: str


class GoogleClient(Protocol):
    def exchange_code(self, code: str, redirect_uri: str) -> Tokens: ...

    def access_token(self, refresh_token: str) -> str: ...

    def revoke(self, refresh_token: str) -> None: ...

    def upsert_event(
        self, access_token: str, calendar_id: str, event_id: str, body: dict[str, Any]
    ) -> str: ...

    def delete_event(self, access_token: str, calendar_id: str, event_id: str) -> None: ...

    def busy(
        self, access_token: str, calendar_id: str, start: datetime, end: datetime
    ) -> list[tuple[datetime, datetime]]: ...


class HttpGoogleClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._http = client or httpx.Client(timeout=20)

    def _check(self, response: httpx.Response) -> dict[str, Any]:
        if response.is_success:
            return response.json() if response.content else {}
        try:
            error = response.json().get("error")
        except ValueError:
            error = None
        code = error if isinstance(error, str) else f"http_{response.status_code}"
        logger.warning("google: %s %s", response.status_code, code)
        if code == "invalid_grant" or response.status_code == 401:
            raise GoogleError("reconnect")
        raise GoogleError(code, retryable=response.status_code in (429, 500, 502, 503, 504))

    def _token(self, data: dict[str, str]) -> dict[str, Any]:
        try:
            response = self._http.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    **data,
                },
            )
        except httpx.HTTPError as exc:
            raise GoogleError("connection", retryable=True) from exc
        return self._check(response)

    def exchange_code(self, code: str, redirect_uri: str) -> Tokens:
        data = self._token(
            {"code": code, "grant_type": "authorization_code", "redirect_uri": redirect_uri}
        )
        access = str(data.get("access_token", ""))
        try:
            info = self._check(
                self._http.get(
                    "https://openidconnect.googleapis.com/v1/userinfo",
                    headers={"Authorization": f"Bearer {access}"},
                )
            )
        except httpx.HTTPError as exc:
            raise GoogleError("connection", retryable=True) from exc
        return Tokens(
            access_token=access,
            refresh_token=str(data.get("refresh_token", "")),
            email=str(info.get("email", "")),
        )

    def access_token(self, refresh_token: str) -> str:
        data = self._token({"refresh_token": refresh_token, "grant_type": "refresh_token"})
        return str(data["access_token"])

    def revoke(self, refresh_token: str) -> None:
        try:
            self._http.post("https://oauth2.googleapis.com/revoke", data={"token": refresh_token})
        except httpx.HTTPError:
            logger.info("google: revogação não confirmada (segue)")

    def _calendar(self, method: str, path: str, token: str, **kwargs: Any) -> dict[str, Any]:
        url = f"https://www.googleapis.com/calendar/v3{path}"
        try:
            response = self._http.request(
                method, url, headers={"Authorization": f"Bearer {token}"}, **kwargs
            )
        except httpx.HTTPError as exc:
            raise GoogleError("connection", retryable=True) from exc
        if method == "DELETE" and response.status_code in (404, 410):
            return {}  # já não existia: tudo certo
        return self._check(response)

    def upsert_event(
        self, access_token: str, calendar_id: str, event_id: str, body: dict[str, Any]
    ) -> str:
        cal = quote(calendar_id, safe="")
        if event_id:
            try:
                data = self._calendar(
                    "PATCH", f"/calendars/{cal}/events/{event_id}", access_token, json=body
                )
                return str(data.get("id", event_id))
            except GoogleError as exc:
                if exc.code != "http_404":
                    raise
        data = self._calendar("POST", f"/calendars/{cal}/events", access_token, json=body)
        return str(data["id"])

    def delete_event(self, access_token: str, calendar_id: str, event_id: str) -> None:
        cal = quote(calendar_id, safe="")
        self._calendar("DELETE", f"/calendars/{cal}/events/{event_id}", access_token)

    def busy(
        self, access_token: str, calendar_id: str, start: datetime, end: datetime
    ) -> list[tuple[datetime, datetime]]:
        data = self._calendar(
            "POST",
            "/freeBusy",
            access_token,
            json={
                "timeMin": start.isoformat(),
                "timeMax": end.isoformat(),
                "timeZone": TZ_NAME,
                "items": [{"id": calendar_id}],
            },
        )
        periods = (data.get("calendars") or {}).get(calendar_id, {}).get("busy", [])
        out = []
        for p in periods:
            s, e = parse_datetime(p.get("start", "")), parse_datetime(p.get("end", ""))
            if s and e:
                out.append((s, e))
        return out


@dataclass
class FakeGoogle:
    """Dev/testes: nada sai da máquina. Os testes mexem em `events` e `busy_blocks`."""

    events: dict[str, dict[str, Any]] = field(default_factory=dict)
    busy_blocks: list[tuple[datetime, datetime]] = field(default_factory=list)
    revoked: list[str] = field(default_factory=list)
    fail_next: GoogleError | None = None

    def _maybe_fail(self) -> None:
        if self.fail_next is not None:
            error, self.fail_next = self.fail_next, None
            raise error

    def exchange_code(self, code: str, redirect_uri: str) -> Tokens:
        self._maybe_fail()
        return Tokens("access-fake", f"refresh-{code}", "advogada@gmail.com")

    def access_token(self, refresh_token: str) -> str:
        self._maybe_fail()
        return "access-fake"

    def revoke(self, refresh_token: str) -> None:
        self.revoked.append(refresh_token)

    def upsert_event(
        self, access_token: str, calendar_id: str, event_id: str, body: dict[str, Any]
    ) -> str:
        self._maybe_fail()
        event_id = event_id or f"g-{uuid.uuid4().hex[:10]}"
        self.events[event_id] = body
        return event_id

    def delete_event(self, access_token: str, calendar_id: str, event_id: str) -> None:
        self._maybe_fail()
        self.events.pop(event_id, None)

    def busy(
        self, access_token: str, calendar_id: str, start: datetime, end: datetime
    ) -> list[tuple[datetime, datetime]]:
        self._maybe_fail()
        return [(s, e) for s, e in self.busy_blocks if s < end and e > start]


@cache
def _fake() -> FakeGoogle:
    return FakeGoogle()


def get_google() -> GoogleClient:
    if settings.GOOGLE_CALENDAR_CLIENT == "fake":
        return _fake()
    if settings.GOOGLE_CALENDAR_CLIENT == "http":
        return HttpGoogleClient()
    raise ImproperlyConfigured("GOOGLE_CALENDAR_CLIENT deve ser http ou fake")


def configured() -> bool:
    return settings.GOOGLE_CALENDAR_CLIENT == "fake" or bool(
        settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET
    )


def redirect_uri() -> str:
    return f"{settings.PUBLIC_API_URL.rstrip('/')}/api/oauth/google/callback/"


# ---------------------------------------------------------------- conectar / desconectar


def authorization_url(*, tenant_id: uuid.UUID, user: User) -> str:
    state = signing.dumps({"t": str(tenant_id), "u": str(user.pk)}, salt=STATE_SALT)
    query = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",  # garante o refresh token mesmo em reconexão
        "include_granted_scopes": "true",
        "state": state,
        "login_hint": user.email,
    }
    return f"{AUTH_URL}?{urlencode(query)}"


def read_state(state: str) -> tuple[uuid.UUID, uuid.UUID]:
    data = signing.loads(state, salt=STATE_SALT, max_age=STATE_MAX_AGE)
    return uuid.UUID(data["t"]), uuid.UUID(data["u"])


def connect(*, tenant_id: uuid.UUID, user_id: uuid.UUID, code: str) -> GoogleCalendarConnection:
    """Volta do Google: troca o código pelo token (fora de transação) e guarda cifrado."""
    tokens = get_google().exchange_code(code, redirect_uri())
    if not tokens.refresh_token:
        raise GoogleError("no_refresh_token")
    with tenant_atomic(tenant_id):
        conn, _ = GoogleCalendarConnection.objects.update_or_create(
            user_id=user_id,
            defaults={
                "refresh_token_encrypted": encrypt_secret(tokens.refresh_token),
                "google_email": tokens.email[:254],
                "needs_reconnect": False,
                "busy_cache": [],
                "busy_synced_at": None,
            },
        )
    refresh_busy(tenant_id, conn.pk)
    return conn


def disconnect(tenant_id: uuid.UUID, user_id: uuid.UUID) -> None:
    with tenant_atomic(tenant_id):
        conn = GoogleCalendarConnection.objects.filter(user_id=user_id).first()
        if conn is None:
            return
        refresh = decrypt_secret(conn.refresh_token_encrypted)
        conn.delete()
    get_google().revoke(refresh)


def _access(tenant_id: uuid.UUID, conn: GoogleCalendarConnection) -> str:
    """Token de acesso (HTTP: chamar fora de transação). Autorização vencida marca reconectar."""
    try:
        return get_google().access_token(decrypt_secret(conn.refresh_token_encrypted))
    except GoogleError as exc:
        if exc.code == "reconnect":
            with tenant_atomic(tenant_id):
                GoogleCalendarConnection.objects.filter(pk=conn.pk).update(needs_reconnect=True)
        raise


# ---------------------------------------------------------------- TramitAI → Google


def event_body(event: Event) -> dict[str, Any]:
    end = event.ends_at or event.starts_at + timedelta(hours=1)
    details = [event.notes] if event.notes else []
    if event.client_id and event.client:
        details.insert(0, f"Cliente: {event.client.name}")
    details.append("Criado pelo TramitAI.")
    return {
        "summary": ("[A confirmar] " if event.status == Event.Status.PENDING else "") + event.title,
        "location": event.location,
        "description": "\n".join(details),
        "start": {"dateTime": event.starts_at.isoformat(), "timeZone": TZ_NAME},
        "end": {"dateTime": end.isoformat(), "timeZone": TZ_NAME},
        "status": "tentative" if event.status == Event.Status.PENDING else "confirmed",
        "transparency": "opaque",
    }


def sync_event(tenant_id: uuid.UUID, event_id: uuid.UUID) -> str:
    """Reflete o compromisso no Google do responsável. Idempotente."""
    with tenant_atomic(tenant_id):
        event = Event.objects.select_related("client").filter(pk=event_id).first()
        if event is None:
            return "missing"
        conn = (
            GoogleCalendarConnection.objects.filter(
                user_id=event.responsible_id, needs_reconnect=False
            ).first()
            if event.responsible_id
            else None
        )
        if conn is None:
            return "not_connected"
        cancel = event.status == Event.Status.CANCELED
        google_id, calendar_id = event.google_event_id, conn.calendar_id
        body = None if cancel else event_body(event)
    token = _access(tenant_id, conn)
    client = get_google()
    if cancel:
        if google_id:
            client.delete_event(token, calendar_id, google_id)
            with tenant_atomic(tenant_id):
                Event.objects.filter(pk=event_id).update(google_event_id="")
        return "deleted"
    new_id = client.upsert_event(token, calendar_id, google_id, body or {})
    if new_id != google_id:
        with tenant_atomic(tenant_id):
            # update() não dispara o sinal de novo (sem laço).
            Event.objects.filter(pk=event_id).update(google_event_id=new_id)
    return "synced"


# ---------------------------------------------------------------- Google → Lia (ocupado)


def refresh_busy(tenant_id: uuid.UUID, connection_id: uuid.UUID) -> str:
    with tenant_atomic(tenant_id):
        conn = GoogleCalendarConnection.objects.filter(
            pk=connection_id, needs_reconnect=False
        ).first()
    if conn is None:
        return "skipped"
    token = _access(tenant_id, conn)
    now = timezone.now()
    periods = get_google().busy(token, conn.calendar_id, now, now + timedelta(days=BUSY_DAYS))
    with tenant_atomic(tenant_id):
        GoogleCalendarConnection.objects.filter(pk=conn.pk).update(
            busy_cache=[[s.isoformat(), e.isoformat()] for s, e in periods],
            busy_synced_at=now,
        )
    return "ok"


def refresh_stale_busy(tenant_id: uuid.UUID, user_id: uuid.UUID | None) -> None:
    """Antes da Lia oferecer horários: atualiza o ocupado se o cache tiver mais de 5 min.
    Falha do Google não impede a resposta (usa o cache que tiver)."""
    if user_id is None:
        return
    with tenant_atomic(tenant_id):
        conn = GoogleCalendarConnection.objects.filter(
            user_id=user_id, needs_reconnect=False
        ).first()
    if conn is None:
        return
    if conn.busy_synced_at and timezone.now() - conn.busy_synced_at < BUSY_STALE:
        return
    try:
        refresh_busy(tenant_id, conn.pk)
    except GoogleError as exc:
        logger.info("google: ocupado não atualizado (%s)", exc.code)


def busy_for(user: User | None) -> list[tuple[datetime, datetime]]:
    """Ocupado do Google em cache (tenant ativo). Sem conexão: lista vazia."""
    if user is None:
        return []
    conn = GoogleCalendarConnection.objects.filter(user=user).first()
    if conn is None:
        return []
    out = []
    for start, end in conn.busy_cache or []:
        s, e = parse_datetime(start), parse_datetime(end)
        if s and e:
            out.append((s, e))
    return out

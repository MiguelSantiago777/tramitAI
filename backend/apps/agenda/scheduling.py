"""Agenda da Lia: horário de atendimento, horários livres, pré-reserva e confirmação.

Fluxo: a Lia recebe os próximos horários livres (já descontando a agenda do advogado), oferece
ao contato, ele escolhe, o horário entra como "A confirmar" e o advogado confirma com um
clique. Só então o contato recebe a confirmação.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from itertools import pairwise
from typing import Any
from zoneinfo import ZoneInfo

from django.db.models import Q
from django.utils import timezone
from rest_framework import status as http_status

from apps.accounts.models import Membership, User
from apps.clientes.models import Client
from apps.core import audit
from apps.core.exceptions import ApiError
from apps.tenants.models import TenantSettings, default_business_hours

from .models import Event

TZ = ZoneInfo("America/Sao_Paulo")
WEEKDAYS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
WEEKDAYS_SHORT = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
# Antecedência mínima para a Lia oferecer um horário.
MIN_LEAD = timedelta(hours=2)
DAYS_AHEAD = 14
SLOTS_TO_OFFER = 3
MODES = {"presencial": "Presencial, no escritório", "online": "Online (vídeo ou telefone)"}

DEFAULT_BUSINESS_HOURS = default_business_hours()


def _t(text: str) -> time:
    hours, minutes = text.split(":")
    return time(int(hours), int(minutes))


def validate_business_hours(value: Any) -> dict[str, list[list[str]]]:
    """{"0": [["09:00","12:00"], ...], ..., "6": []} (0 = segunda). Levanta ValueError."""
    if not isinstance(value, dict):
        raise ValueError("Formato inválido.")
    clean: dict[str, list[list[str]]] = {}
    for day in range(7):
        periods = value.get(str(day), [])
        if not isinstance(periods, list) or len(periods) > 3:
            raise ValueError("Até 3 períodos por dia.")
        out = []
        for period in periods:
            if not (isinstance(period, list) and len(period) == 2):
                raise ValueError("Período inválido.")
            start, end = _t(str(period[0])), _t(str(period[1]))
            if end <= start:
                raise ValueError(f"{WEEKDAYS[day]}: o fim precisa ser depois do início.")
            out.append([start.strftime("%H:%M"), end.strftime("%H:%M")])
        out.sort()
        for (_, prev_end), (next_start, _) in pairwise(out):
            if _t(next_start) < _t(prev_end):
                raise ValueError(f"{WEEKDAYS[day]}: períodos se sobrepõem.")
        clean[str(day)] = out
    return clean


def _periods(cfg: TenantSettings, day: date) -> list[tuple[datetime, datetime]]:
    hours = cfg.business_hours or DEFAULT_BUSINESS_HOURS
    return [
        (
            datetime.combine(day, _t(start), tzinfo=TZ),
            datetime.combine(day, _t(end), tzinfo=TZ),
        )
        for start, end in hours.get(str(day.weekday()), [])
    ]


def is_open(cfg: TenantSettings, now: datetime | None = None) -> bool:
    local = (now or timezone.now()).astimezone(TZ)
    return any(start <= local < end for start, end in _periods(cfg, local.date()))


def hours_text(cfg: TenantSettings) -> str:
    """Ex.: "segunda a sexta, 09:00 às 12:00 e 13:00 às 18:00"."""
    hours = cfg.business_hours or DEFAULT_BUSINESS_HOURS
    groups: list[tuple[list[int], str]] = []
    for day in range(7):
        periods = hours.get(str(day), [])
        if not periods:
            continue
        label = " e ".join(f"{s} às {e}" for s, e in periods)
        if groups and groups[-1][1] == label and groups[-1][0][-1] == day - 1:
            groups[-1][0].append(day)
        else:
            groups.append(([day], label))
    if not groups:
        return "sem horário de atendimento definido"
    parts = []
    for days, label in groups:
        names = (
            WEEKDAYS[days[0]] if len(days) == 1 else f"{WEEKDAYS[days[0]]} a {WEEKDAYS[days[-1]]}"
        )
        parts.append(f"{names}, {label}")
    return "; ".join(parts)


def responsible(cfg: TenantSettings) -> User | None:
    if cfg.scheduling_user_id:
        return cfg.scheduling_user
    owner = (
        Membership.objects.filter(
            tenant_id=cfg.tenant_id, role=Membership.Role.OWNER, is_active=True
        )
        .select_related("user")
        .order_by("created_at")
        .first()
    )
    return owner.user if owner else None


def _busy(user: User | None, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    qs = Event.objects.filter(
        status__in=[Event.Status.SCHEDULED, Event.Status.PENDING],
        starts_at__lt=end,
    ).filter(
        Q(ends_at__gt=start) | Q(ends_at__isnull=True, starts_at__gte=start - timedelta(hours=1))
    )
    if user is not None:
        # Compromisso sem responsável conta como do escritório inteiro.
        qs = qs.filter(Q(responsible=user) | Q(responsible__isnull=True))
    return [(e.starts_at, e.ends_at or e.starts_at + timedelta(hours=1)) for e in qs]


def free_slots(
    cfg: TenantSettings, *, now: datetime | None = None, count: int = SLOTS_TO_OFFER
) -> list[datetime]:
    """Próximos horários livres, espalhados (no máximo 2 por dia) para dar opção real."""
    now = now or timezone.now()
    duration = timedelta(minutes=cfg.consult_minutes)
    earliest = now + MIN_LEAD
    horizon = now + timedelta(days=DAYS_AHEAD)
    busy = _busy(responsible(cfg), now, horizon)
    slots: list[datetime] = []
    day = earliest.astimezone(TZ).date()
    while day <= horizon.astimezone(TZ).date() and len(slots) < count:
        per_day = 0
        for start, end in _periods(cfg, day):
            cursor = start
            while cursor + duration <= end and per_day < 2 and len(slots) < count:
                slot_end = cursor + duration
                clash = any(b_start < slot_end and cursor < b_end for b_start, b_end in busy)
                if cursor >= earliest and not clash:
                    slots.append(cursor)
                    per_day += 1
                    cursor = slot_end + duration  # espaça as opções no mesmo dia
                else:
                    cursor += timedelta(minutes=30)
        day += timedelta(days=1)
    return slots


def slot_label(value: datetime) -> str:
    local = value.astimezone(TZ)
    return f"{WEEKDAYS[local.weekday()]}, {local:%d/%m} às {local:%H:%M}"


def is_free(cfg: TenantSettings, start: datetime) -> bool:
    end = start + timedelta(minutes=cfg.consult_minutes)
    in_hours = any(
        p_start <= start and end <= p_end
        for p_start, p_end in _periods(cfg, start.astimezone(TZ).date())
    )
    if not in_hours or start < timezone.now():
        return False
    return not any(b_s < end and start < b_e for b_s, b_e in _busy(responsible(cfg), start, end))


# ---------------------------------------------------------------- pré-reserva e confirmação


@dataclass(frozen=True)
class Booking:
    event: Event
    label: str


def prebook(
    cfg: TenantSettings, *, client: Client, start: datetime, mode: str, summary: str
) -> Booking | None:
    """Pré-reserva pedida pelo contato (pela Lia). None se o horário não está mais livre."""
    if not is_free(cfg, start):
        return None
    mode = mode if mode in MODES else "presencial"
    event = Event.objects.create(
        title=f"Consulta inicial - {client.name}"[:200],
        kind=Event.Kind.CONSULTATION,
        status=Event.Status.PENDING,
        starts_at=start,
        ends_at=start + timedelta(minutes=cfg.consult_minutes),
        location=MODES[mode],
        notes=f"Marcado pela Lia no WhatsApp. Resumo da triagem: {summary}"[:4000],
        responsible=responsible(cfg),
        client=client,
        remind_client=True,
    )
    audit.record(
        "event.prebooked",
        event,
        actor_type=audit.Actor.AI,
        data={"mode": mode, "client_id": str(client.pk)},
    )
    return Booking(event=event, label=slot_label(start))


def confirmation_text(event: Event) -> str:
    first = (event.client.name if event.client else "").split(" ")[0]
    where = event.location or "no escritório"
    return (
        f"Olá{', ' + first if first else ''}! Sua consulta está confirmada para "
        f"{slot_label(event.starts_at)} ({where}). Na véspera eu te lembro por aqui. "
        "Se precisar remarcar, é só responder."
    )


def confirm(event: Event, *, user: User) -> Event:
    """Advogado confirma a pré-reserva: o contato recebe a confirmação no WhatsApp."""
    from apps.whatsapp import services as whatsapp

    if event.status != Event.Status.PENDING:
        raise ApiError(
            "Este horário não está aguardando confirmação.",
            code="event_not_pending",
            status_code=http_status.HTTP_409_CONFLICT,
        )
    event.status = Event.Status.SCHEDULED
    event.save(update_fields=["status", "updated_at"])
    sent = False
    if event.client is not None:
        conversation = whatsapp.conversation_for_client(event.client)
        if conversation is not None:
            try:
                whatsapp.queue_text(
                    conversation=conversation, body=confirmation_text(event), sent_by=user
                )
                sent = True
            except ApiError:
                sent = False  # janela da Meta fechada: a equipe avisa por outro meio
    audit.record(
        "event.confirmed",
        event,
        actor_type=audit.Actor.USER,
        actor_user=user,
        data={"client_notified": sent},
    )
    return event


def decline(event: Event, *, user: User) -> Event:
    if event.status != Event.Status.PENDING:
        raise ApiError(
            "Este horário não está aguardando confirmação.",
            code="event_not_pending",
            status_code=http_status.HTTP_409_CONFLICT,
        )
    event.status = Event.Status.CANCELED
    event.save(update_fields=["status", "updated_at"])
    audit.record("event.declined", event, actor_type=audit.Actor.USER, actor_user=user)
    return event

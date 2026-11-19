"""Regras de tarefas e agenda."""

import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.accounts.models import User
from apps.core import audit
from apps.core.tenancy import tenant_atomic
from apps.processos.models import CaseMovement, LegalCase, Publication
from apps.tenants.models import Tenant

from .models import Event, Task

logger = logging.getLogger(__name__)
TZ = ZoneInfo(settings.TIME_ZONE)


def today() -> date:
    return timezone.localdate()


# ---------------------------------------------------------------- tarefas a partir de andamentos


@dataclass(frozen=True)
class _Rule:
    pattern: re.Pattern[str]
    kind: str
    title: str
    description: str


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


# Ordem importa: a primeira regra que bate decide. Nenhuma calcula prazo.
MOVEMENT_RULES = [
    _Rule(
        re.compile(r"intima|citac|citad|notifica"),
        Task.Kind.DEADLINE,
        "Verificar prazo: {name}",
        "Andamento de {day} no processo {cnj}. Confira no processo se abre prazo e, se abrir, "
        "registre aqui a data limite. O TramitAI não calcula prazos.",
    ),
    _Rule(
        re.compile(r"audiencia"),
        Task.Kind.TASK,
        "Conferir audiência: {name}",
        "Andamento de {day} no processo {cnj}. Confira data, hora e local da audiência e "
        "cadastre na agenda.",
    ),
    _Rule(
        re.compile(r"sentenca|acordao|julgad|procedente|improcedente|decisao"),
        Task.Kind.TASK,
        "Analisar: {name}",
        "Andamento de {day} no processo {cnj}. Leia a decisão e avalie os próximos passos.",
    ),
]


def create_tasks_for_movements(case: LegalCase) -> int:
    """Tarefas de verificação para andamentos novos importantes (tenant ativo, idempotente)."""
    pending = CaseMovement.objects.filter(
        case=case, notification=CaseMovement.Notification.PENDING
    ).exclude(pk__in=Task.objects.filter(source_movement__isnull=False).values("source_movement"))
    created = 0
    for movement in pending:
        text = _plain(" ".join([movement.name, *map(str, movement.complements)]))
        rule = next((r for r in MOVEMENT_RULES if r.pattern.search(text)), None)
        if rule is None:
            continue
        values = {
            "name": movement.name,
            "day": movement.occurred_at.astimezone(TZ).strftime("%d/%m/%Y"),
            "cnj": case.cnj_formatted,
        }
        task = Task.objects.create(
            title=rule.title.format(**values)[:200],
            description=rule.description.format(**values),
            kind=rule.kind,
            priority=Task.Priority.HIGH,
            due_date=today(),
            assignee=case.responsible,
            legal_case=case,
            client=_main_client(case),
            source=Task.Source.MOVEMENT,
            source_movement=movement,
        )
        audit.record(
            "task.created",
            task,
            actor_type=audit.Actor.SYSTEM,
            data={"source": "movement", "movement_id": str(movement.pk)},
        )
        created += 1
    return created


_PUBLICATION_DEADLINE = re.compile(r"intima|citac|notifica")


def create_tasks_for_publications(publications: list[Publication]) -> int:
    """Uma tarefa por publicação nova do Diário (tenant ativo, idempotente). Nunca calcula prazo."""
    done = set(
        Task.objects.filter(source_publication__in=publications).values_list(
            "source_publication_id", flat=True
        )
    )
    created = 0
    for pub in publications:
        if pub.pk in done:
            continue
        case = pub.legal_case
        kind_label = pub.kind or "Publicação"
        number = pub.cnj_formatted or "sem número"
        is_deadline = bool(_PUBLICATION_DEADLINE.search(_plain(kind_label)))
        title = (
            f"Verificar prazo: {kind_label} — {number}"
            if is_deadline
            else f"Ler publicação: {kind_label} — {number}"
        )
        lines = [
            f"Publicada no Diário (DJEN) em {pub.available_on:%d/%m/%Y}"
            + (f", {pub.tribunal}" if pub.tribunal else "")
            + (f" — {pub.orgao}" if pub.orgao else "")
            + ".",
        ]
        if pub.deadline_hints:
            lines.append("O texto menciona prazo de " + ", ".join(pub.deadline_hints) + ".")
        if case is None:
            lines.append("Processo ainda não cadastrado: cadastre pela tela Publicações.")
        lines.append(
            "Confira no processo se abre prazo e, se abrir, registre aqui a data limite. "
            "O TramitAI não calcula prazos."
        )
        task = Task.objects.create(
            title=title[:200],
            description="\n".join(lines),
            kind=Task.Kind.DEADLINE if is_deadline else Task.Kind.TASK,
            priority=Task.Priority.HIGH,
            due_date=today(),
            assignee=(case.responsible if case and case.responsible else None)
            or (pub.oab.user if pub.oab else None),
            legal_case=case,
            client=_main_client(case) if case else None,
            source=Task.Source.PUBLICATION,
            source_publication=pub,
        )
        audit.record(
            "task.created",
            task,
            actor_type=audit.Actor.SYSTEM,
            data={"source": "publication", "publication_id": str(pub.pk)},
        )
        created += 1
    return created


def _main_client(case: LegalCase):  # type: ignore[no-untyped-def]
    link = case.case_clients.select_related("client").order_by("created_at").first()
    return link.client if link else None


# ---------------------------------------------------------------- concluir / reabrir


def complete_task(task: Task, *, user: User) -> Task:
    if task.status != Task.Status.DONE:
        task.status = Task.Status.DONE
        task.completed_at = timezone.now()
        task.completed_by = user
        task.save(update_fields=["status", "completed_at", "completed_by", "updated_at"])
        audit.record("task.completed", task, actor_type=audit.Actor.USER, actor_user=user)
    return task


def reopen_task(task: Task, *, user: User) -> Task:
    if task.status != Task.Status.OPEN:
        task.status = Task.Status.OPEN
        task.completed_at = None
        task.completed_by = None
        task.save(update_fields=["status", "completed_at", "completed_by", "updated_at"])
        audit.record("task.reopened", task, actor_type=audit.Actor.USER, actor_user=user)
    return task


# ---------------------------------------------------------------- minha mesa


@dataclass(frozen=True)
class Desk:
    overdue: list[Task]
    today: list[Task]
    upcoming: list[Task]
    no_date: list[Task]
    events_today: list[Event]
    events_upcoming: list[Event]


def _mine(qs: QuerySet[Task], user: User) -> QuerySet[Task]:
    # As minhas e as sem responsável (alguém precisa pegar).
    return qs.filter(Q(assignee=user) | Q(assignee__isnull=True))


def my_desk(user: User) -> Desk:
    day = today()
    week = day + timedelta(days=7)
    open_tasks = _mine(
        Task.objects.filter(status=Task.Status.OPEN).select_related(
            "assignee", "client", "legal_case"
        ),
        user,
    )
    start = datetime.combine(day, datetime.min.time(), tzinfo=TZ)
    events = (
        Event.objects.filter(status=Event.Status.SCHEDULED, starts_at__gte=start)
        .filter(Q(responsible=user) | Q(responsible__isnull=True))
        .select_related("responsible", "client", "legal_case")
        .order_by("starts_at")
    )
    tomorrow = start + timedelta(days=1)
    return Desk(
        overdue=list(open_tasks.filter(due_date__lt=day).order_by("due_date")[:50]),
        today=list(open_tasks.filter(due_date=day).order_by("due_time", "created_at")[:50]),
        upcoming=list(
            open_tasks.filter(due_date__gt=day, due_date__lte=week).order_by("due_date")[:50]
        ),
        no_date=list(open_tasks.filter(due_date__isnull=True).order_by("-created_at")[:20]),
        events_today=list(events.filter(starts_at__lt=tomorrow)[:20]),
        events_upcoming=list(
            events.filter(starts_at__gte=tomorrow, starts_at__lt=start + timedelta(days=8))[:20]
        ),
    )


# ---------------------------------------------------------------- lembrete de compromisso

_KIND_PHRASE: dict[str, str] = {
    Event.Kind.HEARING: "sua audiência está marcada",
    Event.Kind.MEETING: "nossa reunião está marcada",
    Event.Kind.CONSULTATION: "seu atendimento está marcado",
    Event.Kind.OTHER: "seu compromisso está marcado",
}


def _hour(local: datetime) -> str:
    return f"{local:%H}h" if local.minute == 0 else f"{local:%H}h{local:%M}"


def reminder_text(event: Event, first_name: str) -> str:
    """Texto fixo (sem IA): só dados que o escritório cadastrou."""
    local = event.starts_at.astimezone(TZ)
    greeting = f"Olá, {first_name}!" if first_name else "Olá!"
    text = (
        f"{greeting} Passando para lembrar: {_KIND_PHRASE[event.kind]} "
        f"para {local:%d/%m} às {_hour(local)}"
    )
    if event.location:
        text += f", em {event.location}"
    return text + ". Qualquer dúvida, é só responder esta mensagem."


def create_event_reminders() -> int:
    """Beat: compromissos de amanhã com "lembrar o cliente" viram rascunho para aprovação."""
    from apps.aprovacoes import services as approvals
    from apps.aprovacoes.models import OutboundDraft
    from apps.whatsapp import services as whatsapp

    now = timezone.now()
    window_start, window_end = now + timedelta(hours=12), now + timedelta(hours=36)
    total = 0
    for tenant_id in Tenant.objects.filter(status=Tenant.Status.ACTIVE).values_list(
        "id", flat=True
    ):
        with tenant_atomic(tenant_id):
            due = Event.objects.select_for_update(of=("self",)).filter(
                status=Event.Status.SCHEDULED,
                remind_client=True,
                client__isnull=False,
                client_reminded_at__isnull=True,
                starts_at__gte=window_start,
                starts_at__lt=window_end,
            )
            for event in due.select_related("client", "legal_case"):
                client = event.client
                if client is None:  # filtrado acima; só para o type checker
                    continue
                conversation = whatsapp.conversation_for_client(client)
                event.client_reminded_at = now
                event.save(update_fields=["client_reminded_at", "updated_at"])
                if conversation is None:
                    audit.record(
                        "event.reminder_skipped",
                        event,
                        actor_type=audit.Actor.SYSTEM,
                        data={"reason": "no_whatsapp"},
                    )
                    continue
                local = event.starts_at.astimezone(TZ)
                approvals.create_draft(
                    conversation=conversation,
                    origin=OutboundDraft.Origin.EVENT_REMINDER,
                    body=reminder_text(event, (client.name or "").split(" ")[0]),
                    actor_type=audit.Actor.SYSTEM,
                    client=client,
                    legal_case=event.legal_case,
                    summary=(
                        f"Lembrete de {event.get_kind_display().lower()} "
                        f"em {local:%d/%m às %H:%M}: {event.title}"
                    ),
                )
                total += 1
    if total:
        logger.info("agenda: %s lembretes criados", total)
    return total

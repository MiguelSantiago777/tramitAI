"""Linha do tempo do cliente (ficha 360°): tudo o que aconteceu com ele, mais recente primeiro.

Junta várias fontes (atendimentos, tarefas, agenda, WhatsApp, processos, andamentos, termo).
Paginação por cursor de data (`before`): cada fonte traz até `limit` itens anteriores ao
cursor; o resultado é mesclado e cortado em `limit`.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from apps.agenda.models import Event, Task
from apps.documentos.services import for_client
from apps.processos.models import CaseMovement, LegalCase
from apps.whatsapp.models import Message

from .models import Client, ClientNote, ClientTermAcceptance

PREVIEW = 280


@dataclass(frozen=True)
class TimelineItem:
    id: str
    type: str  # note | task | task_done | event | message | case | movement | document | term
    at: datetime
    title: str
    body: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


def _name(user: Any) -> str:
    return (user.full_name or user.email) if user else ""


def client_timeline(
    client: Client, *, before: datetime | None = None, limit: int = 30
) -> tuple[list[TimelineItem], datetime | None]:
    def until(qs: Any, field_name: str) -> Any:
        return qs.filter(**{f"{field_name}__lt": before}) if before else qs

    items: list[TimelineItem] = []
    # Um a mais por fonte: se sobrar, sabemos que existe página seguinte.
    fetch = limit + 1

    notes = until(ClientNote.objects.filter(client=client), "created_at")
    for n in notes.select_related("author", "legal_case").order_by("-created_at")[:fetch]:
        items.append(
            TimelineItem(
                id=str(n.pk),
                type="note",
                at=n.created_at,
                title=n.get_kind_display(),
                body=n.body,
                meta={
                    "author": _name(n.author),
                    "kind": n.kind,
                    "case_number": n.legal_case.cnj_formatted if n.legal_case else "",
                },
            )
        )

    tasks = Task.objects.filter(client=client).select_related("assignee", "completed_by")
    for t in until(tasks, "created_at").order_by("-created_at")[:fetch]:
        items.append(
            TimelineItem(
                id=str(t.pk),
                type="task",
                at=t.created_at,
                title=f"{t.get_kind_display()}: {t.title}",
                meta={
                    "task_id": str(t.pk),
                    "status": t.status,
                    "due_date": t.due_date.isoformat() if t.due_date else None,
                    "assignee": _name(t.assignee),
                },
            )
        )
    done = tasks.filter(completed_at__isnull=False)
    for t in until(done, "completed_at").order_by("-completed_at")[:fetch]:
        if t.completed_at is None:  # filtrado acima; só para o type checker
            continue
        items.append(
            TimelineItem(
                id=f"{t.pk}:done",
                type="task_done",
                at=t.completed_at,
                title=f"Concluída: {t.title}",
                meta={"task_id": str(t.pk), "by": _name(t.completed_by)},
            )
        )

    events = until(Event.objects.filter(client=client), "starts_at")
    for e in events.order_by("-starts_at")[:fetch]:
        items.append(
            TimelineItem(
                id=str(e.pk),
                type="event",
                at=e.starts_at,
                title=f"{e.get_kind_display()}: {e.title}",
                body=e.location,
                meta={"event_id": str(e.pk), "status": e.status},
            )
        )

    messages = until(Message.objects.filter(conversation__client=client), "created_at")
    for m in messages.select_related("sent_by").order_by("-created_at")[:fetch]:
        inbound = m.direction == Message.Direction.INBOUND
        items.append(
            TimelineItem(
                id=str(m.pk),
                type="message",
                at=m.created_at,
                title="Cliente escreveu" if inbound else "Escritório respondeu",
                body=(m.body or f"[{m.get_type_display()}]")[:PREVIEW],
                meta={
                    "conversation_id": str(m.conversation_id),
                    "direction": m.direction,
                    "by": _name(m.sent_by),
                },
            )
        )

    cases = LegalCase.objects.filter(case_clients__client=client).distinct()
    for c in until(cases, "created_at").order_by("-created_at")[:fetch]:
        items.append(
            TimelineItem(
                id=str(c.pk),
                type="case",
                at=c.created_at,
                title="Processo cadastrado",
                meta={"case_id": str(c.pk), "case_number": c.cnj_formatted},
            )
        )

    movements = until(
        CaseMovement.objects.filter(case__case_clients__client=client), "occurred_at"
    ).distinct()
    for mv in movements.select_related("case").order_by("-occurred_at")[:fetch]:
        items.append(
            TimelineItem(
                id=str(mv.pk),
                type="movement",
                at=mv.occurred_at,
                title=mv.name,
                body="; ".join(str(c) for c in mv.complements),
                meta={
                    "case_id": str(mv.case_id),
                    "case_number": mv.case.cnj_formatted,
                    "notification": mv.notification,
                },
            )
        )

    documents = until(for_client(client), "created_at").select_related("uploaded_by")
    for d in documents.order_by("-created_at")[:fetch]:
        items.append(
            TimelineItem(
                id=str(d.pk),
                type="document",
                at=d.created_at,
                title=(
                    "Cliente enviou um arquivo pelo WhatsApp"
                    if d.source == "WHATSAPP"
                    else "Documento adicionado"
                ),
                body=d.name,
                meta={
                    "document_id": str(d.pk),
                    "by": _name(d.uploaded_by),
                    "content_type": d.content_type,
                },
            )
        )

    terms = until(ClientTermAcceptance.objects.filter(client=client), "accepted_at")
    for a in terms.select_related("term_version").order_by("-accepted_at")[:fetch]:
        items.append(
            TimelineItem(
                id=str(a.pk),
                type="term",
                at=a.accepted_at,
                title=f"Aceitou o termo de IA (versão {a.term_version.version})",
                meta={"channel": a.channel},
            )
        )

    items.sort(key=lambda i: i.at, reverse=True)
    page = items[:limit]
    next_before = page[-1].at if len(items) > limit else None
    return page, next_before

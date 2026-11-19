"""Relatórios do escritório: números do período para o titular acompanhar o negócio.

Só agregados (contagens e somas). Nada de conteúdo de mensagem.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from django.db.models import Count, F, Q, Sum
from django.utils import timezone

from apps.agenda.models import Task
from apps.aprovacoes.models import OutboundDraft
from apps.clientes.models import Client
from apps.financeiro.models import Installment
from apps.financeiro.services import add_months
from apps.funil.models import Opportunity
from apps.processos.models import CaseMovement, LegalCase
from apps.whatsapp.models import Message

TZ = ZoneInfo("America/Sao_Paulo")
MAX_DAYS = 366


@dataclass(frozen=True)
class MonthPoint:
    month: date
    received: Decimal
    expected: Decimal


@dataclass(frozen=True)
class Overview:
    start: date
    end: date
    clients: dict[str, int]
    funnel: dict[str, Any]
    whatsapp: dict[str, int]
    ai: dict[str, Any]
    cases: dict[str, int]
    tasks: dict[str, int]
    finance: dict[str, Decimal | int]
    finance_months: list[MonthPoint] = field(default_factory=list)


def _range(start: date, end: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(start, time.min, tzinfo=TZ),
        datetime.combine(end, time.max, tzinfo=TZ),
    )


def _pct(part: int, whole: int) -> float:
    return round(100 * part / whole, 1) if whole else 0.0


def overview(start: date, end: date) -> Overview:
    t0, t1 = _range(start, end)
    in_period = {"created_at__gte": t0, "created_at__lte": t1}

    clients = Client.objects.filter(**in_period).aggregate(
        new_clients=Count("id", filter=~Q(status=Client.Status.LEAD)),
        new_leads=Count("id", filter=Q(status=Client.Status.LEAD)),
    )
    clients["total_active"] = Client.objects.filter(status=Client.Status.ACTIVE).count()

    opps = Opportunity.objects.all()
    created = opps.filter(**in_period).count()
    closed = opps.filter(closed_at__gte=t0, closed_at__lte=t1)
    won = closed.filter(stage=Opportunity.Stage.WON)
    lost = closed.filter(stage=Opportunity.Stage.LOST)
    by_source = dict(
        opps.filter(**in_period).values_list("source").annotate(n=Count("id")).order_by()
    )
    funnel: dict[str, Any] = {
        "created": created,
        "won": won.count(),
        "lost": lost.count(),
        "conversion": _pct(won.count(), won.count() + lost.count()),
        "won_value": won.aggregate(v=Sum("estimated_value"))["v"] or Decimal("0"),
        "open_now": opps.filter(stage__in=Opportunity.OPEN_STAGES).count(),
        "by_source": {str(k): v for k, v in by_source.items()},
        "lost_reasons": dict(
            lost.exclude(lost_reason="")
            .values_list("lost_reason")
            .annotate(n=Count("id"))
            .order_by("-n")[:5]
        ),
    }

    messages = Message.objects.filter(**in_period).aggregate(
        inbound=Count("id", filter=Q(direction=Message.Direction.INBOUND)),
        outbound=Count("id", filter=Q(direction=Message.Direction.OUTBOUND)),
        conversations=Count("conversation", distinct=True),
    )

    drafts = OutboundDraft.objects.filter(**in_period)
    decided = drafts.filter(decided_at__isnull=False)
    approved = decided.exclude(status=OutboundDraft.Status.REJECTED).exclude(
        status=OutboundDraft.Status.DRAFT
    )
    ai_drafts = drafts.filter(origin=OutboundDraft.Origin.AI_REPLY)
    ai_approved = approved.filter(origin=OutboundDraft.Origin.AI_REPLY)
    unedited = ai_approved.filter(final_body=F("generated_body")).count()
    ai: dict[str, Any] = {
        "drafts": drafts.count(),
        "ai_drafts": ai_drafts.count(),
        "approved": approved.count(),
        "rejected": decided.filter(status=OutboundDraft.Status.REJECTED).count(),
        "pending_now": OutboundDraft.objects.filter(status=OutboundDraft.Status.DRAFT).count(),
        # Quanto do texto da Vera saiu sem edição: mede se a IA está ajudando de verdade.
        "ai_unedited_pct": _pct(unedited, ai_approved.count()),
    }

    cases = {
        "active": LegalCase.objects.filter(status=LegalCase.Status.ACTIVE).count(),
        "new": LegalCase.objects.filter(**in_period).count(),
        "movements": CaseMovement.objects.filter(occurred_at__gte=t0, occurred_at__lte=t1).count(),
        "notified": CaseMovement.objects.filter(
            occurred_at__gte=t0,
            occurred_at__lte=t1,
            notification=CaseMovement.Notification.NOTIFIED,
        ).count(),
    }

    today = timezone.localdate()
    tasks = {
        "done": Task.objects.filter(
            status=Task.Status.DONE, completed_at__gte=t0, completed_at__lte=t1
        ).count(),
        "open_now": Task.objects.filter(status=Task.Status.OPEN).count(),
        "overdue_now": Task.objects.filter(status=Task.Status.OPEN, due_date__lt=today).count(),
    }

    paid = Installment.objects.filter(
        status=Installment.Status.PAID, paid_at__gte=t0, paid_at__lte=t1
    )
    open_qs = Installment.objects.filter(status=Installment.Status.OPEN)
    finance: dict[str, Decimal | int] = {
        "received": paid.aggregate(v=Sum("paid_amount"))["v"] or Decimal("0"),
        "received_count": paid.count(),
        "via_mercadopago": paid.filter(settled_by__isnull=True).count(),
        "overdue_now": open_qs.filter(due_date__lt=today).aggregate(v=Sum("amount"))["v"]
        or Decimal("0"),
        "open_now": open_qs.aggregate(v=Sum("amount"))["v"] or Decimal("0"),
    }

    return Overview(
        start=start,
        end=end,
        clients=clients,
        funnel=funnel,
        whatsapp=messages,
        ai=ai,
        cases=cases,
        tasks=tasks,
        finance=finance,
        finance_months=finance_months(end),
    )


def finance_months(end: date, months: int = 6) -> list[MonthPoint]:
    """Recebido x previsto nos últimos meses (gráfico de barras)."""
    points = []
    last_first = end.replace(day=1)
    for i in range(months - 1, -1, -1):
        first = add_months(last_first, -i)
        last = add_months(first, 1) - timedelta(days=1)
        t0, t1 = _range(first, last)
        received = Installment.objects.filter(
            status=Installment.Status.PAID, paid_at__gte=t0, paid_at__lte=t1
        ).aggregate(v=Sum("paid_amount"))["v"] or Decimal("0")
        expected = Installment.objects.filter(due_date__gte=first, due_date__lte=last).exclude(
            status=Installment.Status.CANCELLED
        ).aggregate(v=Sum("amount"))["v"] or Decimal("0")
        points.append(MonthPoint(month=first, received=received, expected=expected))
    return points

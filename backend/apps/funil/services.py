"""Regras do funil."""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import status as http_status

from apps.accounts.models import User
from apps.clientes.models import Client
from apps.core import audit
from apps.core.exceptions import ApiError
from apps.whatsapp.models import Conversation

from .models import Opportunity


def _renumber(stage: str, *, insert: Opportunity | None = None, at: int | None = None) -> None:
    """Reordena a coluna (0, 1, 2...), opcionalmente colocando `insert` na posição `at`."""
    items = list(
        Opportunity.objects.filter(stage=stage)
        .exclude(pk=insert.pk if insert else None)
        .order_by("position", "-created_at")
    )
    if insert is not None:
        index = len(items) if at is None else max(0, min(at, len(items)))
        items.insert(index, insert)
    for index, item in enumerate(items):
        if item.position != index:
            Opportunity.objects.filter(pk=item.pk).update(position=index)
            item.position = index


def create_opportunity(*, user: User | None, **fields: object) -> Opportunity:
    opportunity = Opportunity(created_by=user, **fields)
    opportunity.position = 0
    opportunity.save()
    _renumber(opportunity.stage, insert=opportunity, at=0)  # novo entra no topo da coluna
    audit.record(
        "opportunity.created",
        opportunity,
        actor_type=audit.Actor.USER if user else audit.Actor.SYSTEM,
        actor_user=user,
        data={"stage": opportunity.stage, "source": opportunity.source},
    )
    return opportunity


def move_opportunity(
    opportunity: Opportunity,
    *,
    stage: str,
    position: int | None,
    user: User,
    lost_reason: str = "",
) -> Opportunity:
    """Arrasta no quadro. Contratou: o lead vira cliente ativo. Não contratou: pede motivo."""
    previous = opportunity.stage
    if stage == Opportunity.Stage.LOST and not (lost_reason or opportunity.lost_reason).strip():
        raise ApiError(
            "Conte o motivo (ex.: achou caro, resolveu sozinho). Ajuda a melhorar o atendimento.",
            code="lost_reason_required",
            status_code=http_status.HTTP_400_BAD_REQUEST,
        )
    fields = ["stage", "position", "updated_at"]
    if stage != previous:
        opportunity.stage = stage
        opportunity.stage_changed_at = timezone.now()
        fields.append("stage_changed_at")
        closing = stage in (Opportunity.Stage.WON, Opportunity.Stage.LOST)
        opportunity.closed_at = timezone.now() if closing else None
        fields.append("closed_at")
    if stage == Opportunity.Stage.LOST:
        opportunity.lost_reason = (lost_reason or opportunity.lost_reason).strip()[:255]
        fields.append("lost_reason")
    elif stage != Opportunity.Stage.LOST and opportunity.lost_reason:
        opportunity.lost_reason = ""
        fields.append("lost_reason")
    opportunity.save(update_fields=fields)
    _renumber(stage, insert=opportunity, at=position)
    if stage != previous:
        _renumber(previous)
        audit.record(
            "opportunity.stage_changed",
            opportunity,
            actor_type=audit.Actor.USER,
            actor_user=user,
            data={"from": previous, "to": stage},
        )
        if stage == Opportunity.Stage.WON:
            _activate_client(opportunity.client, user)
    opportunity.refresh_from_db()
    return opportunity


def _activate_client(client: Client, user: User) -> None:
    if client.status == Client.Status.LEAD:
        client.status = Client.Status.ACTIVE
        client.save(update_fields=["status", "updated_at"])
        audit.record(
            "client.converted",
            client,
            actor_type=audit.Actor.USER,
            actor_user=user,
            data={"from": "LEAD"},
        )


def ensure_whatsapp_opportunity(conversation: Conversation, summary: str) -> Opportunity | None:
    """Triagem viu "caso novo": entra no funil (uma oportunidade aberta por cliente)."""
    client = conversation.client
    if client is None or client.status == Client.Status.ARCHIVED:
        return None
    exists = Opportunity.objects.filter(client=client, stage__in=Opportunity.OPEN_STAGES).exists()
    if exists:
        return None
    return create_opportunity(
        user=None,
        title=f"Caso novo de {client.name}"[:200],
        client=client,
        source=Opportunity.Source.WHATSAPP,
        conversation=conversation,
        owner=conversation.assignee,
        notes=summary[:2000],
    )


def board_summary(days: int = 90) -> dict[str, object]:
    """Números do funil: abertas por etapa, valor em aberto, conversão nos últimos N dias."""
    since = timezone.now() - timedelta(days=days)
    open_qs = Opportunity.objects.filter(stage__in=Opportunity.OPEN_STAGES)
    by_stage: dict[str, int] = dict(
        open_qs.order_by().values("stage").annotate(total=Count("id")).values_list("stage", "total")
    )
    closed = Opportunity.objects.filter(closed_at__gte=since).aggregate(
        won=Count("id", filter=Q(stage=Opportunity.Stage.WON)),
        lost=Count("id", filter=Q(stage=Opportunity.Stage.LOST)),
    )
    won, lost = closed["won"], closed["lost"]
    open_value = open_qs.aggregate(total=Sum("estimated_value"))["total"] or Decimal("0")
    won_value = Opportunity.objects.filter(
        stage=Opportunity.Stage.WON, closed_at__gte=since
    ).aggregate(total=Sum("estimated_value"))["total"] or Decimal("0")
    return {
        "open_count": sum(by_stage.values()),
        "by_stage": {stage: by_stage.get(stage, 0) for stage in Opportunity.OPEN_STAGES},
        "open_value": open_value,
        "won_count": won,
        "lost_count": lost,
        "won_value": won_value,
        "conversion_rate": round(won / (won + lost), 3) if won + lost else None,
        "period_days": days,
    }

"""Monitoramento de andamentos (ProcessSource → CaseMovement).

Três fases, como no resto do projeto: lê o processo numa transação curta, consulta a fonte
FORA de transação e grava numa transação curta com o processo travado (select_for_update),
então duas consultas simultâneas do mesmo processo não duplicam nem perdem andamento.

Primeira consulta bem-sucedida = linha de base: o histórico encontrado ali não vira aviso
ao cliente. Depois disso, cada andamento novo (recente) fica PENDING e dispara o sinal
`movements_detected`, que a IA usa para escrever o rascunho de aviso.
"""

import hashlib
import json
import logging
import uuid
from datetime import UTC, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status as http_status

from apps.accounts.models import User
from apps.core import audit
from apps.core.exceptions import ApiError
from apps.core.tenancy import tenant_atomic
from apps.tenants.models import Tenant

from .models import CaseMovement, LegalCase
from .signals import movements_detected
from .sources import CaseSnapshot, Movement, SourceError, get_process_source

logger = logging.getLogger(__name__)

MANUAL_CHECK_COOLDOWN = timedelta(minutes=2)


class RetryableSyncError(Exception):
    """Falha temporária na fonte; a task tenta de novo com backoff."""


def fingerprint(movement: Movement) -> str:
    key = json.dumps(
        [
            movement.grau,
            movement.code,
            movement.occurred_at.astimezone(UTC).isoformat(),
            movement.name,
            sorted(movement.complements),
        ],
        ensure_ascii=False,
    )
    return hashlib.sha256(key.encode()).hexdigest()


def sync_case(tenant_id: uuid.UUID, case_id: uuid.UUID) -> str:
    """Consulta a fonte e grava os andamentos novos. Idempotente. Devolve um código."""
    with tenant_atomic(tenant_id):
        case = LegalCase.objects.filter(pk=case_id).first()
        if case is None:
            return "missing"
        if case.status != LegalCase.Status.ACTIVE or not case.monitoring_enabled:
            return "disabled"
        if not case.tribunal_alias:
            _record_error(case_id, "unknown_tribunal")
            return "error:unknown_tribunal"
        cnj, alias = case.cnj_number, case.tribunal_alias

    source = get_process_source()
    try:
        snapshot = source.fetch(cnj, alias)
    except SourceError as exc:
        with tenant_atomic(tenant_id):
            _record_error(case_id, exc.code)
        logger.warning("monitoring: processo %s erro %s", case_id, exc.code)
        if exc.retryable:
            raise RetryableSyncError(exc.code) from exc
        return f"error:{exc.code}"

    with tenant_atomic(tenant_id):
        outcome = ingest_snapshot(case_id, snapshot, source=source.name)
    logger.info("monitoring: processo %s → %s", case_id, outcome)
    return outcome


def _record_error(case_id: uuid.UUID, code: str) -> None:
    LegalCase.objects.filter(pk=case_id).update(
        sync_status=LegalCase.SyncStatus.ERROR,
        sync_error=code[:64],
        last_checked_at=timezone.now(),
    )


def ingest_snapshot(case_id: uuid.UUID, snapshot: CaseSnapshot | None, *, source: str) -> str:
    """Grava o snapshot (tenant ativo, dentro de transação)."""
    case = LegalCase.objects.select_for_update().get(pk=case_id)
    now = timezone.now()
    case.last_checked_at = now
    case.sync_error = ""
    if snapshot is None:
        case.sync_status = LegalCase.SyncStatus.NOT_FOUND
        case.save(update_fields=["last_checked_at", "sync_status", "sync_error", "updated_at"])
        return "not_found"

    is_baseline = case.baseline_at is None
    cutoff = now - timedelta(days=settings.MOVEMENT_NOTIFY_MAX_AGE_DAYS)
    known = set(CaseMovement.objects.filter(case=case).values_list("fingerprint", flat=True))
    new: list[CaseMovement] = []
    for movement in snapshot.movements:
        fp = fingerprint(movement)
        if fp in known:
            continue
        known.add(fp)
        notify = not is_baseline and movement.occurred_at >= cutoff
        new.append(
            CaseMovement(
                tenant_id=case.tenant_id,
                case=case,
                source=source,
                fingerprint=fp,
                code=movement.code,
                name=movement.name[:255],
                complements=list(movement.complements),
                grau=movement.grau[:8],
                occurred_at=movement.occurred_at,
                notification=(
                    CaseMovement.Notification.PENDING
                    if notify
                    else CaseMovement.Notification.BASELINE
                ),
            )
        )
    CaseMovement.objects.bulk_create(new)

    fields = ["last_checked_at", "sync_status", "sync_error", "updated_at"]
    case.sync_status = LegalCase.SyncStatus.OK
    if is_baseline:
        case.baseline_at = now
        fields.append("baseline_at")
    if new:
        latest = max(m.occurred_at for m in new)
        if case.last_movement_at is None or latest > case.last_movement_at:
            case.last_movement_at = latest
            fields.append("last_movement_at")
    # Completa o cadastro com dados públicos do tribunal, sem sobrescrever o que o escritório
    # digitou.
    for field, value in (
        ("classe", snapshot.classe),
        ("assunto", snapshot.assuntos[0] if snapshot.assuntos else ""),
        ("orgao_julgador", snapshot.orgao_julgador),
    ):
        if value and not getattr(case, field):
            setattr(case, field, value[:255])
            fields.append(field)
    case.save(update_fields=fields)

    pending = [m for m in new if m.notification == CaseMovement.Notification.PENDING]
    if pending:
        audit.record(
            "case.movements_detected",
            case,
            actor_type=audit.Actor.SYSTEM,
            data={"count": len(pending), "source": source},
        )
        movements_detected.send(sender=LegalCase, case=case)
    if is_baseline:
        return f"baseline:{len(new)}"
    return f"new:{len(pending)}" if pending else "unchanged"


def schedule_due_checks() -> int:
    """Beat: agenda a consulta dos processos que estão há mais de N horas sem checagem.

    Espalha as tasks no tempo (DataJud é público e devolve 429 com facilidade).
    """
    from .tasks import sync_case_task

    due_before = timezone.now() - timedelta(hours=settings.CASE_CHECK_INTERVAL_HOURS)
    budget = settings.CASE_CHECKS_PER_RUN
    scheduled = 0
    tenant_ids = Tenant.objects.filter(status=Tenant.Status.ACTIVE).values_list("id", flat=True)
    for tenant_id in tenant_ids:
        if scheduled >= budget:
            break
        with tenant_atomic(tenant_id):
            case_ids = list(
                LegalCase.objects.filter(
                    Q(last_checked_at__isnull=True) | Q(last_checked_at__lt=due_before),
                    status=LegalCase.Status.ACTIVE,
                    monitoring_enabled=True,
                )
                .exclude(tribunal_alias="")
                .order_by("last_checked_at")
                .values_list("id", flat=True)[: budget - scheduled]
            )
        for case_id in case_ids:
            countdown = scheduled * settings.CASE_CHECK_SPACING_SECONDS
            sync_case_task.apply_async(args=[str(tenant_id), str(case_id)], countdown=countdown)
            scheduled += 1
    if scheduled:
        logger.info("monitoring: %s processos agendados", scheduled)
    return scheduled


def request_check(case: LegalCase, *, user: User) -> None:
    """Botão "Verificar agora". Tem um intervalo mínimo para não martelar o DataJud."""
    from .tasks import sync_case_task

    if case.status != LegalCase.Status.ACTIVE or not case.monitoring_enabled:
        raise ApiError(
            "Ative o monitoramento deste processo para consultar o andamento.",
            code="monitoring_disabled",
            status_code=http_status.HTTP_409_CONFLICT,
        )
    if case.last_checked_at and timezone.now() - case.last_checked_at < MANUAL_CHECK_COOLDOWN:
        raise ApiError(
            "Este processo acabou de ser consultado. Tente de novo em alguns minutos.",
            code="checked_recently",
            status_code=http_status.HTTP_429_TOO_MANY_REQUESTS,
        )
    audit.record("case.check_requested", case, actor_type=audit.Actor.USER, actor_user=user)
    args = [str(case.tenant_id), str(case.pk)]
    transaction.on_commit(lambda: sync_case_task.apply_async(args=args))

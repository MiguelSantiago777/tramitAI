"""Publicações do Diário (DJEN) por OAB → Publication (+ tarefa de verificação na agenda).

Mesmo padrão do monitoramento de andamentos: lê numa transação curta, consulta a fonte FORA
de transação e grava numa transação curta com a OAB travada. Publicação é deduplicada pelo id
do DJEN (único por escritório), então duas OABs no mesmo processo não duplicam.

Publicação de processo cadastrado também pede uma consulta ao DataJud na hora (o andamento
costuma aparecer lá dias depois, mas não custa tentar).
"""

import logging
import uuid
from datetime import date, timedelta
from functools import partial

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status as http_status

from apps.accounts.models import User
from apps.core import audit
from apps.core.exceptions import ApiError
from apps.core.tenancy import tenant_atomic
from apps.tenants.models import Tenant

from .models import LegalCase, MonitoredOab, Publication
from .monitoring import RetryableSyncError
from .signals import publications_detected
from .sources import SourceError, get_publication_source
from .sources.djen import Communication, deadline_hints

logger = logging.getLogger(__name__)

MANUAL_CHECK_COOLDOWN = timedelta(minutes=2)
# Janela máxima de uma busca (OAB pausada por meses não puxa o ano inteiro).
MAX_WINDOW_DAYS = 30
# Só publicação recente vira tarefa; o resto fica só na lista.
TASK_MAX_AGE_DAYS = 7


def feature_enabled(tenant_id: uuid.UUID) -> bool:
    """Plano do escritório inclui publicações? Isento/sem plano = sim."""
    from apps.cobranca.limits import plan_for

    plan = plan_for(tenant_id)
    return plan is None or plan.includes_publications


def require_feature(tenant_id: uuid.UUID) -> None:
    if not feature_enabled(tenant_id):
        raise ApiError(
            "As publicações do Diário fazem parte dos planos Escritório e Equipe. "
            "Mude de plano em Assinatura para usar.",
            code="plan_feature",
            status_code=http_status.HTTP_402_PAYMENT_REQUIRED,
        )


def _today() -> date:
    return timezone.localdate()


def fetch_window(oab: MonitoredOab, today: date) -> tuple[date, date]:
    """Recomeça 1 dia antes do último sucesso (publicação do dia pode sair mais tarde)."""
    if oab.fetched_until:
        start = oab.fetched_until - timedelta(days=1)
    else:
        start = today - timedelta(days=settings.PUBLICATION_INITIAL_DAYS)
    return max(start, today - timedelta(days=MAX_WINDOW_DAYS)), today


def sync_oab(tenant_id: uuid.UUID, oab_id: uuid.UUID) -> str:
    """Busca as publicações da OAB e grava as novas. Idempotente. Devolve um código."""
    today = _today()
    with tenant_atomic(tenant_id):
        oab = MonitoredOab.objects.filter(pk=oab_id).first()
        if oab is None:
            return "missing"
        if not oab.is_active:
            return "disabled"
        number, uf = oab.number, oab.uf
        start, end = fetch_window(oab, today)

    source = get_publication_source()
    try:
        items = source.fetch(number, uf, start, end)
    except SourceError as exc:
        with tenant_atomic(tenant_id):
            MonitoredOab.objects.filter(pk=oab_id).update(
                last_error=exc.code[:64], last_checked_at=timezone.now()
            )
        logger.warning("publicacoes: oab %s erro %s", oab_id, exc.code)
        if exc.retryable:
            raise RetryableSyncError(exc.code) from exc
        return f"error:{exc.code}"

    with tenant_atomic(tenant_id):
        new = ingest(oab_id, items, fetched_until=end, today=today)
    logger.info("publicacoes: oab %s → %s nova(s)", oab_id, len(new))
    return f"new:{len(new)}" if new else "unchanged"


def ingest(
    oab_id: uuid.UUID, items: list[Communication], *, fetched_until: date, today: date
) -> list[Publication]:
    """Grava as comunicações novas (tenant ativo, dentro de transação)."""
    oab = MonitoredOab.objects.select_for_update().get(pk=oab_id)
    known = set(
        Publication.objects.filter(djen_id__in=[i.djen_id for i in items]).values_list(
            "djen_id", flat=True
        )
    )
    cnjs = {i.cnj_number for i in items if i.cnj_number}
    cases = {c.cnj_number: c for c in LegalCase.objects.filter(cnj_number__in=cnjs)}

    new: list[Publication] = []
    for item in items:
        if item.djen_id in known:
            continue
        known.add(item.djen_id)
        publication = Publication(
            djen_id=item.djen_id,
            oab=oab,
            legal_case=cases.get(item.cnj_number),
            cnj_number=item.cnj_number,
            tribunal=item.tribunal,
            kind=item.kind,
            document_type=item.document_type,
            orgao=item.orgao,
            classe=item.classe,
            available_on=item.available_on,
            text=item.text,
            link=item.link,
            recipients=list(item.recipients),
            deadline_hints=deadline_hints(item.text),
        )
        try:
            # Outra OAB do escritório pode ter gravado a mesma publicação agora.
            with transaction.atomic():
                publication.save()
        except IntegrityError:
            continue
        new.append(publication)

    oab.last_checked_at = timezone.now()
    oab.fetched_until = fetched_until
    oab.last_error = ""
    oab.save(update_fields=["last_checked_at", "fetched_until", "last_error", "updated_at"])

    if new:
        audit.record(
            "publications.detected",
            oab,
            actor_type=audit.Actor.SYSTEM,
            data={"count": len(new)},
        )
        recent = [p for p in new if p.available_on >= today - timedelta(days=TASK_MAX_AGE_DAYS)]
        if recent:
            publications_detected.send(sender=Publication, publications=recent)
        _refresh_cases({p.legal_case for p in new if p.legal_case is not None})
    return new


def _refresh_cases(cases: set[LegalCase]) -> None:
    from .tasks import sync_case_task

    for case in cases:
        if case.status == LegalCase.Status.ACTIVE and case.monitoring_enabled:
            args = [str(case.tenant_id), str(case.pk)]
            transaction.on_commit(partial(sync_case_task.apply_async, args=args))


def schedule_due_checks() -> int:
    """Beat: agenda a busca de todas as OABs ativas, uma por vez (o DJEN limita requisições)."""
    from .tasks import sync_oab_task

    scheduled = 0
    tenant_ids = Tenant.objects.filter(status=Tenant.Status.ACTIVE).values_list("id", flat=True)
    for tenant_id in tenant_ids:
        if not feature_enabled(tenant_id):
            continue
        with tenant_atomic(tenant_id):
            oab_ids = list(
                MonitoredOab.objects.filter(is_active=True)
                .order_by("last_checked_at")
                .values_list("id", flat=True)
            )
        for oab_id in oab_ids:
            countdown = scheduled * settings.PUBLICATION_CHECK_SPACING_SECONDS
            sync_oab_task.apply_async(args=[str(tenant_id), str(oab_id)], countdown=countdown)
            scheduled += 1
    if scheduled:
        logger.info("publicacoes: %s OAB(s) agendadas", scheduled)
    return scheduled


def request_check(oab: MonitoredOab, *, user: User) -> None:
    """Botão "Buscar agora"."""
    from .tasks import sync_oab_task

    require_feature(oab.tenant_id)
    if not oab.is_active:
        raise ApiError(
            "Ative o monitoramento desta OAB para buscar as publicações.",
            code="monitoring_disabled",
            status_code=http_status.HTTP_409_CONFLICT,
        )
    if oab.last_checked_at and timezone.now() - oab.last_checked_at < MANUAL_CHECK_COOLDOWN:
        raise ApiError(
            "Esta OAB acabou de ser consultada. Tente de novo em alguns minutos.",
            code="checked_recently",
            status_code=http_status.HTTP_429_TOO_MANY_REQUESTS,
        )
    audit.record("oab.check_requested", oab, actor_type=audit.Actor.USER, actor_user=user)
    args = [str(oab.tenant_id), str(oab.pk)]
    transaction.on_commit(lambda: sync_oab_task.apply_async(args=args))


# ------------------------------------------------------------------------- ações do usuário


def set_status(publication: Publication, status: str, *, user: User) -> Publication:
    if publication.status != status:
        publication.status = status
        handled = status != Publication.Status.NEW
        publication.handled_at = timezone.now() if handled else None
        publication.handled_by = user if handled else None
        publication.save(update_fields=["status", "handled_at", "handled_by", "updated_at"])
        audit.record(
            "publication.status_changed",
            publication,
            actor_type=audit.Actor.USER,
            actor_user=user,
            data={"status": status},
        )
    return publication


def link_case(case: LegalCase) -> int:
    """Processo cadastrado: amarra as publicações (e tarefas delas) que já tinham esse número."""
    from apps.agenda.models import Task

    pubs = Publication.objects.filter(cnj_number=case.cnj_number, legal_case__isnull=True)
    ids = list(pubs.values_list("id", flat=True))
    if not ids:
        return 0
    Publication.objects.filter(pk__in=ids).update(legal_case=case)
    Task.objects.filter(source_publication_id__in=ids, legal_case__isnull=True).update(
        legal_case=case
    )
    return len(ids)


def _nice_case(text: str) -> str:
    """'PROCEDIMENTO COMUM CíVEL' → 'Procedimento comum cível' (o DJEN manda em maiúsculas)."""
    letters = [c for c in text if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) > len(letters) / 2:
        return text.capitalize()
    return text


@transaction.atomic
def create_case_from(publication: Publication, *, user: User) -> LegalCase:
    """Cadastra o processo da publicação (ou devolve o que já existe com esse número)."""
    from .services import create_case

    if not publication.cnj_number:
        raise ApiError(
            "Esta publicação não traz o número do processo.",
            code="no_cnj",
            status_code=http_status.HTTP_400_BAD_REQUEST,
        )
    if LegalCase.with_deleted.filter(
        cnj_number=publication.cnj_number, deleted_at__isnull=False
    ).exists():
        raise ApiError(
            "Este processo está na Lixeira. Restaure-o por lá.",
            code="case_in_trash",
            status_code=http_status.HTTP_409_CONFLICT,
        )
    case = LegalCase.objects.filter(cnj_number=publication.cnj_number).first()
    if case is None:
        responsible = publication.oab.user if publication.oab else None
        case = create_case(
            links=[],
            cnj_number=publication.cnj_number,
            classe=_nice_case(publication.classe),
            orgao_julgador=publication.orgao,
            responsible=responsible or user,
        )
        audit.record(
            "case.created_from_publication",
            case,
            actor_type=audit.Actor.USER,
            actor_user=user,
            data={"publication_id": str(publication.pk)},
        )
    link_case(case)
    publication.refresh_from_db()
    return case

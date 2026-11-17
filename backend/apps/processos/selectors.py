import uuid

from django.db.models import Count, Q, QuerySet

from apps.core.br import only_digits

from .models import CaseMovement, LegalCase


def cases_with_relations() -> QuerySet[LegalCase]:
    return (
        LegalCase.objects.select_related("responsible")
        .prefetch_related("case_clients__client")
        .annotate(
            pending_movement_count=Count(
                "movements",
                filter=Q(movements__notification=CaseMovement.Notification.PENDING),
                distinct=True,
            )
        )
    )


def search_cases(
    *, q: str = "", status: str = "", client_id: uuid.UUID | None = None
) -> QuerySet[LegalCase]:
    """Busca por número CNJ (parcial), nome do cliente, classe ou assunto (tenant ativo)."""
    qs = cases_with_relations()
    if status:
        qs = qs.filter(status=status)
    if client_id:
        qs = qs.filter(case_clients__client_id=client_id)
    q = q.strip()
    if q:
        condition = (
            Q(case_clients__client__name__icontains=q)
            | Q(classe__icontains=q)
            | Q(assunto__icontains=q)
        )
        digits = only_digits(q)
        if digits:
            condition |= Q(cnj_number__contains=digits)
        qs = qs.filter(condition).distinct()
    return qs.order_by("-created_at")


def cnj_in_use(cnj_number: str, *, exclude_id: object = None) -> bool:
    qs = LegalCase.objects.filter(cnj_number=cnj_number)
    if exclude_id is not None:
        qs = qs.exclude(pk=exclude_id)
    return qs.exists()

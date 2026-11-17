from django.db.models import Q, QuerySet

from apps.core.br import normalize_document, only_digits

from .models import Client, ClientTermAcceptance


def search_clients(*, q: str = "", status: str = "") -> QuerySet[Client]:
    """Busca por nome, e-mail, CPF/CNPJ ou telefone (tenant ativo)."""
    qs = Client.objects.all()
    if status:
        qs = qs.filter(status=status)
    q = q.strip()
    if q:
        condition = Q(name__icontains=q) | Q(email__icontains=q)
        digits = only_digits(q)
        if digits:
            condition |= Q(cpf_cnpj__contains=normalize_document(q))
        if len(digits) >= 4:
            condition |= Q(phone_e164__contains=digits)
        qs = qs.filter(condition)
    return qs.order_by("name")


def document_in_use(document: str, *, exclude_id: object = None) -> bool:
    qs = Client.objects.filter(cpf_cnpj=document)
    if exclude_id is not None:
        qs = qs.exclude(pk=exclude_id)
    return qs.exists()


def term_acceptances(client: Client) -> QuerySet[ClientTermAcceptance]:
    return client.term_acceptances.select_related("term_version", "recorded_by").order_by(
        "-accepted_at"
    )

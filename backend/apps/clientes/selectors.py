import uuid

from django.db.models import Q, QuerySet

from apps.core.br import normalize_document, only_digits

from .models import Client, ClientTermAcceptance


def clients_with_tags() -> QuerySet[Client]:
    return Client.objects.prefetch_related("client_tags__tag")


def search_clients(
    *, q: str = "", status: str = "", tag_id: uuid.UUID | None = None
) -> QuerySet[Client]:
    """Busca por nome, e-mail, CPF/CNPJ ou telefone (tenant ativo)."""
    qs = clients_with_tags()
    if status:
        qs = qs.filter(status=status)
    if tag_id:
        qs = qs.filter(client_tags__tag_id=tag_id)
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


def document_owner(document: str, *, exclude_id: object = None) -> Client | None:
    """Cliente (inclusive na lixeira) que já usa este CPF/CNPJ."""
    qs = Client.with_deleted.filter(cpf_cnpj=document)
    if exclude_id is not None:
        qs = qs.exclude(pk=exclude_id)
    return qs.first()


def document_in_use(document: str, *, exclude_id: object = None) -> bool:
    return document_owner(document, exclude_id=exclude_id) is not None


def term_acceptances(client: Client) -> QuerySet[ClientTermAcceptance]:
    return client.term_acceptances.select_related("term_version", "recorded_by").order_by(
        "-accepted_at"
    )

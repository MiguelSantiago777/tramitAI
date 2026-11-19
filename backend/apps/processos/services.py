from dataclasses import dataclass
from typing import Any

from django.db import transaction

from apps.clientes.models import Client

from .models import CaseClient, LegalCase


@dataclass(frozen=True)
class ClientLink:
    client: Client
    role: str


@transaction.atomic
def create_case(*, links: list[ClientLink], **data: Any) -> LegalCase:
    from .publications import link_case

    case = LegalCase.objects.create(**data)
    _replace_links(case, links)
    link_case(case)
    return case


@transaction.atomic
def update_case(case: LegalCase, *, links: list[ClientLink] | None, **data: Any) -> LegalCase:
    """Atualiza o processo. `links=None` mantém os clientes; lista (mesmo vazia) substitui."""
    for field, value in data.items():
        setattr(case, field, value)
    case.save()
    if links is not None:
        _replace_links(case, links)
    return case


def _replace_links(case: LegalCase, links: list[ClientLink]) -> None:
    wanted = {link.client.pk: link.role for link in links}
    existing = {cc.client_id: cc for cc in CaseClient.objects.filter(case=case)}

    for client_id, case_client in existing.items():
        if client_id not in wanted:
            case_client.delete()
        elif case_client.role != wanted[client_id]:
            case_client.role = wanted[client_id]
            case_client.save(update_fields=["role", "updated_at"])

    for link in links:
        if link.client.pk not in existing:
            CaseClient.objects.create(case=case, client=link.client, role=link.role)

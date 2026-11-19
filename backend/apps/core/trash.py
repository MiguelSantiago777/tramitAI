"""Lixeira de clientes e processos.

Remover = some de todas as listas na hora (manager `objects` filtra deleted_at), sem apagar
nada. Por 30 dias dá para restaurar. Depois disso (ou no "Apagar de vez" do titular) o
registro é apagado de verdade com o que depende dele, inclusive os arquivos no disco.

A auditoria guarda só ids (append-only), então continua mostrando que o registro existiu.
"""

import logging
import uuid
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone
from rest_framework import status as http_status

from apps.accounts.models import Membership, User
from apps.core import audit
from apps.core.exceptions import ApiError
from apps.core.tenancy import tenant_atomic

logger = logging.getLogger(__name__)

RETENTION = timedelta(days=30)


def can_remove(membership: Membership) -> bool:
    """Titular e advogado(a) removem; a equipe não."""
    return membership.role in (Membership.Role.OWNER, Membership.Role.LAWYER)


def require_can_remove(membership: Membership) -> None:
    if not can_remove(membership):
        raise ApiError(
            "Só titular ou advogado(a) pode remover clientes e processos.",
            code="permission_denied",
            status_code=http_status.HTTP_403_FORBIDDEN,
        )


def open_installments(client: Any) -> int:
    from apps.financeiro.models import Installment

    return Installment.objects.filter(
        agreement__client=client, status=Installment.Status.OPEN
    ).count()


def trash_client(client: Any, *, user: User, force: bool = False) -> None:
    pending = open_installments(client)
    if pending and not force:
        raise ApiError(
            f"Este cliente tem {pending} parcela(s) de honorários em aberto. "
            "Remova mesmo assim só se não for mais cobrar.",
            code="has_open_installments",
            status_code=http_status.HTTP_409_CONFLICT,
        )
    _trash(client, user=user, action="client.trashed", data={"open_installments": pending})


def trash_case(case: Any, *, user: User) -> None:
    _trash(case, user=user, action="case.trashed")


def _trash(obj: Any, *, user: User, action: str, data: dict[str, Any] | None = None) -> None:
    if obj.deleted_at is not None:
        return
    obj.deleted_at = timezone.now()
    obj.deleted_by = user
    obj.save(update_fields=["deleted_at", "deleted_by", "updated_at"])
    audit.record(action, obj, actor_type=audit.Actor.USER, actor_user=user, data=data)


def restore(obj: Any, *, user: User) -> None:
    from apps.clientes.models import Client
    from apps.processos.models import LegalCase
    from apps.processos.publications import link_case

    if obj.deleted_at is None:
        return
    if isinstance(obj, Client) and obj.cpf_cnpj:
        clash = Client.objects.filter(cpf_cnpj=obj.cpf_cnpj).exclude(pk=obj.pk).exists()
        if clash:
            raise ApiError(
                "Já existe outro cliente com este CPF/CNPJ. Remova ou ajuste o outro antes.",
                code="document_in_use",
                status_code=http_status.HTTP_409_CONFLICT,
            )
    obj.deleted_at = None
    obj.deleted_by = None
    obj.save(update_fields=["deleted_at", "deleted_by", "updated_at"])
    if isinstance(obj, LegalCase):
        link_case(obj)
    kind = "client" if isinstance(obj, Client) else "case"
    audit.record(f"{kind}.restored", obj, actor_type=audit.Actor.USER, actor_user=user)


# ------------------------------------------------------------------------- apagar de vez


def purge_client(client: Any, *, user: User | None = None) -> None:
    """Apaga o cliente e o que só existe por causa dele (tenant ativo, em transação)."""
    from apps.documentos.models import Document
    from apps.financeiro.models import FeeAgreement
    from apps.funil.models import Opportunity
    from apps.processos.models import CaseClient

    _audit_purge("client.purged", client, user)
    for document in Document.objects.filter(client=client):
        document.delete()  # apaga o arquivo do disco depois do commit
    FeeAgreement.objects.filter(client=client).delete()  # parcelas em cascata
    Opportunity.objects.filter(client=client).delete()
    CaseClient.objects.filter(client=client).delete()
    if client.term_acceptances.exists():
        # O aceite do termo é prova (append-only no banco): fica, preso a um cadastro vazio.
        client.service_notes.all().delete()
        client.client_tags.all().delete()
        client.name = "Cliente removido"
        client.cpf_cnpj = client.phone_e164 = client.email = client.notes = ""
        client.anonymized_at = timezone.now()
        client.save()
        return
    client.delete()


def purge_case(case: Any, *, user: User | None = None) -> None:
    """Apaga o processo (andamentos e vínculos em cascata; tarefas/publicações ficam soltas)."""
    _audit_purge("case.purged", case, user)
    case.delete()


def _audit_purge(action: str, obj: Any, user: User | None) -> None:
    audit.record(
        action,
        obj,
        actor_type=audit.Actor.USER if user else audit.Actor.SYSTEM,
        actor_user=user,
    )


def purge_expired() -> int:
    """Beat diário: apaga de vez o que está na lixeira há mais de 30 dias (por escritório)."""
    from apps.clientes.models import Client
    from apps.processos.models import LegalCase
    from apps.tenants.models import Tenant

    limit = timezone.now() - RETENTION
    purged = 0
    for tenant_id in Tenant.objects.values_list("id", flat=True):
        purged += _purge_tenant(tenant_id, limit, Client, LegalCase)
    if purged:
        logger.info("lixeira: %s registro(s) apagados de vez", purged)
    return purged


def _purge_tenant(tenant_id: uuid.UUID, limit: Any, client_model: Any, case_model: Any) -> int:
    purged = 0
    with tenant_atomic(tenant_id):
        for case in case_model.with_deleted.filter(deleted_at__lt=limit):
            with transaction.atomic():
                purge_case(case)
            purged += 1
        expired = client_model.with_deleted.filter(deleted_at__lt=limit, anonymized_at__isnull=True)
        for client in expired:
            with transaction.atomic():
                purge_client(client)
            purged += 1
    return purged

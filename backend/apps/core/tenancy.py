"""Contexto de tenant: a trava de aplicação + a variável de sessão do Postgres (RLS).

Duas camadas:
1. Um ContextVar com o tenant corrente. O manager de TenantModel filtra por ele e levanta
   TenantContextMissing quando não há tenant ativo (falha fechada).
2. `set_config('app.tenant_id', ..., is_local=true)` na transação corrente. As policies de RLS
   comparam tenant_id com essa variável; sem ela, nenhuma linha é visível nem gravável.

`is_local=true` faz a variável morrer no fim da transação, então ela nunca vaza para o próximo
uso da conexão (persistente ou via pool). Por isso tudo aqui exige transação aberta.

Regra do projeto: chamadas HTTP/LLM nunca dentro de transação aberta. Em tasks, use
`tenant_atomic()` em blocos curtos: lê, sai da transação, chama o serviço externo, grava.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from django.db import connection, transaction

_current_tenant: ContextVar[uuid.UUID | None] = ContextVar("current_tenant", default=None)


class TenantContextMissing(RuntimeError):
    """Acesso a dado de tenant sem tenant ativo."""


class TenantMismatch(RuntimeError):
    """Tentativa de gravar registro de um tenant estando com outro tenant ativo."""


def get_current_tenant_id() -> uuid.UUID:
    tenant_id = _current_tenant.get()
    if tenant_id is None:
        raise TenantContextMissing("Nenhum tenant ativo neste contexto.")
    return tenant_id


def peek_current_tenant_id() -> uuid.UUID | None:
    return _current_tenant.get()


def _set_db_tenant(value: str) -> None:
    if not connection.in_atomic_block:
        raise TenantContextMissing(
            "O tenant só pode ser ativado dentro de transaction.atomic() "
            "(set_config com is_local=true)."
        )
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", [value])


def _get_db_tenant() -> str:
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('app.tenant_id', true)")
        row = cursor.fetchone()
    return (row[0] if row else None) or ""


def activate_tenant(tenant_id: uuid.UUID) -> None:
    """Ativa o tenant até o fim da transação/request. Usado pela autenticação."""
    _set_db_tenant(str(tenant_id))
    _current_tenant.set(tenant_id)


def clear_tenant() -> None:
    """Limpa o ContextVar. A variável do banco morre sozinha no fim da transação."""
    _current_tenant.set(None)


@contextmanager
def tenant_context(tenant_id: uuid.UUID) -> Iterator[None]:
    """Ativa um tenant dentro de uma transação já aberta e restaura o anterior ao sair."""
    previous_db = _get_db_tenant()
    _set_db_tenant(str(tenant_id))
    token = _current_tenant.set(tenant_id)
    try:
        yield
    finally:
        _current_tenant.reset(token)
        if not connection.needs_rollback:
            _set_db_tenant(previous_db)


@contextmanager
def tenant_atomic(tenant_id: uuid.UUID) -> Iterator[None]:
    """Transação curta já com o tenant ativo. Para tasks Celery e comandos."""
    with transaction.atomic(), tenant_context(tenant_id):
        yield

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.clientes.models import Client
from apps.core.tenancy import tenant_context
from apps.processos import monitoring
from apps.processos.models import CaseClient, LegalCase
from apps.processos.sources import CaseSnapshot, FakeProcessSource, Movement, get_process_source
from apps.processos.tests.factories import make_cnj


@pytest.fixture
def fake_source() -> FakeProcessSource:
    source = get_process_source()
    assert isinstance(source, FakeProcessSource)
    source.snapshots.clear()
    source.calls.clear()
    source.fail_next = None
    return source


def movement(name: str, when: datetime | None = None, **extra: Any) -> Movement:
    return Movement(name=name, occurred_at=when or timezone.now() - timedelta(days=1), **extra)


OLD = datetime(2024, 3, 4, 13, 0, tzinfo=UTC)


@pytest.fixture
def monitored_case(tenant_a: Any, fake_source: FakeProcessSource) -> LegalCase:
    """Processo do TJRJ com a cliente Maria (telefone com WhatsApp) e um andamento antigo."""
    with tenant_context(tenant_a.tenant.id):
        maria = Client.objects.create(
            name="Maria da Silva", cpf_cnpj="52998224725", phone_e164="+5521998765432"
        )
        case = LegalCase.objects.create(cnj_number=make_cnj())
        CaseClient.objects.create(case=case, client=maria, role=CaseClient.Role.AUTHOR)
    fake_source.snapshots[case.cnj_number] = CaseSnapshot(
        cnj_number=case.cnj_number,
        classe="Procedimento Comum Cível",
        assuntos=("Indenização por Dano Moral",),
        orgao_julgador="1ª Vara Cível de Nova Iguaçu",
        movements=(movement("Distribuição", OLD, code=26),),
    )
    return case


@pytest.fixture
def sync(
    tenant_a: Any, fake_source: FakeProcessSource, django_capture_on_commit_callbacks: Any
) -> Callable[..., str]:
    """Roda a consulta (e o que ela agenda depois do commit, eager)."""

    def _sync(case: LegalCase, *new: Movement) -> str:
        if new:
            current = fake_source.snapshots[case.cnj_number]
            assert current is not None
            fake_source.snapshots[case.cnj_number] = replace(
                current, movements=(*current.movements, *new)
            )
        with django_capture_on_commit_callbacks(execute=True):
            return monitoring.sync_case(tenant_a.tenant.id, case.pk)

    return _sync

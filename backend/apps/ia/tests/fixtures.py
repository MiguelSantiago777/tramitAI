from collections.abc import Callable
from typing import Any

import pytest

from apps.aprovacoes.models import OutboundDraft
from apps.core.tenancy import tenant_context
from apps.ia.llm import FakeLlmClient, get_llm_client


@pytest.fixture
def fake_llm() -> FakeLlmClient:
    client = get_llm_client()
    assert isinstance(client, FakeLlmClient)
    client.queue.clear()
    client.calls.clear()
    return client


@pytest.fixture
def drafts(tenant_a: Any) -> Callable[..., list[OutboundDraft]]:
    def _drafts(**filters: Any) -> list[OutboundDraft]:
        with tenant_context(tenant_a.tenant.id):
            return list(
                OutboundDraft.objects.filter(**filters)
                .select_related("generation", "term_version")
                .order_by("created_at")
            )

    return _drafts


@pytest.fixture
def approve(tenant_a: Any, django_capture_on_commit_callbacks: Any) -> Callable[..., Any]:
    """Aprova um rascunho como o titular e roda o envio (gateway fake)."""
    from apps.aprovacoes.services import approve_draft

    def _approve(draft: OutboundDraft, body: str | None = None) -> OutboundDraft:
        with (
            tenant_context(tenant_a.tenant.id),
            django_capture_on_commit_callbacks(execute=True),
        ):
            result = approve_draft(
                draft=draft, user=tenant_a.owner, membership=tenant_a.membership, body=body
            )
        return result

    return _approve

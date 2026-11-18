"""Triagem automática: a Lia conversa sozinha com contato novo e passa para o advogado."""

import pytest

from apps.aprovacoes.models import OutboundDraft
from apps.clientes.models import Client
from apps.core.tenancy import tenant_atomic, tenant_context
from apps.ia.services import HANDOFF_ACK, MAX_AUTO_REPLIES_PER_DAY
from apps.tenants.models import TenantSettings

pytestmark = pytest.mark.django_db

TERM = OutboundDraft.Origin.TERM_REQUEST
AI = OutboundDraft.Origin.AI_REPLY


def _llm(reply, *, complete=False, needs_lawyer=False, urgency="normal"):
    return {
        "intent": "new_matter",
        "needs_lawyer": needs_lawyer,
        "triage_complete": complete,
        "urgency": urgency,
        "summary_for_lawyer": "Contato quer ajuda com demissão.",
        "reply": reply,
    }


@pytest.fixture
def auto_on(tenant_a):
    with tenant_atomic(tenant_a.tenant.id):
        TenantSettings.objects.update(auto_send_simple_replies=True)


def _accepted(inbound, approve, drafts):
    inbound("Oi, fui demitido")
    approve(drafts(origin=TERM)[0])


def _sent(fake_gateway):
    return [m.body for m in fake_gateway.sent]


def test_lia_asks_alone_then_hands_off_to_lawyer(
    tenant_a, account_a, auto_on, inbound, approve, drafts, fake_llm, fake_gateway
):
    _accepted(inbound, approve, drafts)
    fake_llm.queue.append(_llm("Sinto muito! Qual é o seu nome completo?"))
    inbound("Aceito")

    [first] = drafts(origin=AI)
    assert first.auto_sent is True
    assert first.status in (OutboundDraft.Status.APPROVED, OutboundDraft.Status.SENT)
    assert _sent(fake_gateway)[-1] == "Sinto muito! Qual é o seu nome completo?"

    # Já tem nome e resumo: o rascunho vai para o advogado e o contato recebe o aviso.
    fake_llm.queue.append(
        _llm("Olá, João! Podemos marcar uma conversa para amanhã?", complete=True)
    )
    inbound("João da Silva. Fui demitido ontem sem receber nada.")
    pending = drafts(origin=AI, status=OutboundDraft.Status.DRAFT)
    assert [d.generated_body for d in pending] == [
        "Olá, João! Podemos marcar uma conversa para amanhã?"
    ]
    assert pending[0].auto_sent is False
    assert _sent(fake_gateway)[-1] == HANDOFF_ACK

    # Nova mensagem antes do advogado responder: não repete o aviso.
    count = len(fake_gateway.sent)
    fake_llm.queue.append(_llm("Anotado.", complete=True))
    inbound("Ah, trabalhei lá 5 anos")
    assert len(fake_gateway.sent) == count


def test_off_by_default_everything_waits_for_approval(
    tenant_a, account_a, inbound, approve, drafts, fake_llm, fake_gateway
):
    _accepted(inbound, approve, drafts)
    sent_before = len(fake_gateway.sent)
    fake_llm.queue.append(_llm("Qual é o seu nome?"))
    inbound("Aceito")
    [draft] = drafts(origin=AI)
    assert draft.status == OutboundDraft.Status.DRAFT
    assert len(fake_gateway.sent) == sent_before


def test_existing_client_always_goes_to_approval(
    tenant_a, account_a, auto_on, inbound, approve, drafts, fake_llm, fake_gateway
):
    _accepted(inbound, approve, drafts)
    fake_llm.queue.append(_llm("Qual é o seu nome?"))
    inbound("Aceito")
    with tenant_atomic(tenant_a.tenant.id):
        Client.objects.update(status=Client.Status.ACTIVE)
    fake_llm.queue.append(_llm("O processo está na fase de provas."))
    inbound("Como está meu processo?")
    pending = drafts(origin=AI, status=OutboundDraft.Status.DRAFT)
    assert [d.generated_body for d in pending] == ["O processo está na fase de provas."]


@pytest.mark.parametrize(
    "kwargs", [{"needs_lawyer": True}, {"urgency": "high"}], ids=["needs_lawyer", "urgent"]
)
def test_urgent_or_lawyer_question_goes_to_approval_with_ack(
    tenant_a, account_a, auto_on, inbound, approve, drafts, fake_llm, fake_gateway, kwargs
):
    _accepted(inbound, approve, drafts)
    fake_llm.queue.append(_llm("Qual é o seu nome?"))
    inbound("Aceito")
    fake_llm.queue.append(_llm("Vou passar para a advogada agora.", **kwargs))
    inbound("Tenho audiência amanhã!")
    [draft] = drafts(origin=AI, status=OutboundDraft.Status.DRAFT)
    assert draft.generated_body == "Vou passar para a advogada agora."
    assert _sent(fake_gateway)[-1] == HANDOFF_ACK


def test_guardrail_flag_blocks_auto_send(
    tenant_a, account_a, auto_on, inbound, approve, drafts, fake_llm, fake_gateway
):
    _accepted(inbound, approve, drafts)
    fake_llm.queue.append(_llm("Seu processo 0001234-56.2024.8.19.0001 já foi julgado."))
    inbound("Aceito")
    [draft] = drafts(origin=AI)
    assert draft.status == OutboundDraft.Status.DRAFT
    assert draft.guardrail_flags


def test_daily_cap_on_automatic_replies(
    tenant_a, account_a, auto_on, inbound, approve, drafts, fake_llm, fake_gateway
):
    _accepted(inbound, approve, drafts)
    fake_llm.queue.append(_llm("Pergunta 1"))
    inbound("Aceito")
    with tenant_context(tenant_a.tenant.id):
        draft = OutboundDraft.objects.get(origin=AI)
        conversation = draft.conversation
    with tenant_atomic(tenant_a.tenant.id):
        for _ in range(MAX_AUTO_REPLIES_PER_DAY):
            OutboundDraft.objects.create(
                conversation=conversation,
                origin=AI,
                generated_body="x",
                status=OutboundDraft.Status.SENT,
                auto_sent=True,
            )
    fake_llm.queue.append(_llm("Pergunta 9"))
    inbound("mais uma")
    pending = drafts(origin=AI, status=OutboundDraft.Status.DRAFT)
    assert [d.generated_body for d in pending] == ["Pergunta 9"]

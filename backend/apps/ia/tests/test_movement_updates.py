from datetime import timedelta

import pytest
from django.utils import timezone

from apps.aprovacoes.models import OutboundDraft
from apps.aprovacoes.services import reject_draft
from apps.clientes.models import Client
from apps.core.models import AuditEvent
from apps.core.tenancy import tenant_context
from apps.ia import movements as movement_service
from apps.ia.llm import LlmError
from apps.ia.models import AiGeneration
from apps.processos.models import CaseClient, CaseMovement
from apps.processos.tests.fixtures import movement
from apps.tenants.models import TenantSettings
from apps.whatsapp.models import Message, WhatsAppAccount
from apps.whatsapp.tests.fixtures import NUMBER_A, status_payload

MARIA_WA = "5521998765432"


def _updates(drafts, **filters):
    return drafts(origin=OutboundDraft.Origin.MOVEMENT_UPDATE, **filters)


def _movements(tenant_a, case):
    with tenant_context(tenant_a.tenant.id):
        return {m.name: m for m in CaseMovement.objects.filter(case=case)}


@pytest.fixture
def baseline(account_a, monitored_case, sync):
    sync(monitored_case)
    return monitored_case


def test_baseline_never_notifies(tenant_a, account_a, monitored_case, sync, drafts, fake_llm):
    sync(monitored_case)
    assert _updates(drafts) == []
    assert fake_llm.calls == []


def test_new_movement_becomes_draft_with_plain_language_text(
    tenant_a, baseline, sync, drafts, fake_llm
):
    sync(baseline, movement("Conclusão", code=51))

    [draft] = _updates(drafts)
    assert draft.status == OutboundDraft.Status.DRAFT
    assert draft.generated_body.startswith("Olá, Maria! [IA de teste]")
    assert draft.legal_case_id == baseline.pk
    assert draft.client_relevant is True
    assert draft.needs_lawyer is True
    assert draft.generation.kind == AiGeneration.Kind.MOVEMENT_UPDATE
    assert draft.generation.legal_case_id == baseline.pk
    conclusao = _movements(tenant_a, baseline)["Conclusão"]
    assert draft.movement_ids == [str(conclusao.pk)]

    [call] = fake_llm.calls
    assert call.purpose == "movement_update"
    assert baseline.cnj_formatted in call.user_content
    assert "Conclusão" in call.user_content
    assert "papel do cliente: Autor" in call.user_content
    # Distribuição é histórico: entra só como contexto anterior.
    assert "<andamentos_anteriores>\n- 04/03/2024: Distribuição" in call.user_content
    # Nada de dado pessoal do cliente vai para o LLM.
    for personal in ("Maria", "52998224725", "998765432"):
        assert personal not in call.user_content


def test_ai_disabled_uses_fixed_text_from_court_data(tenant_a, baseline, sync, drafts, fake_llm):
    with tenant_context(tenant_a.tenant.id):
        TenantSettings.objects.update(ai_triage_enabled=False)
    when = timezone.now() - timedelta(days=1)
    sync(baseline, movement("Conclusão", when))

    [draft] = _updates(drafts)
    assert fake_llm.calls == []
    assert draft.generation is None
    assert baseline.cnj_formatted in draft.generated_body
    assert "Conclusão em" in draft.generated_body
    assert draft.needs_lawyer is True


def test_guardrail_violation_falls_back_and_keeps_original_for_lawyer(
    tenant_a, baseline, sync, drafts, fake_llm
):
    fake_llm.queue.append(
        {
            "message": "O juiz deu prazo de 15 dias para você juntar os documentos.",
            "client_relevant": True,
            "needs_lawyer": False,
            "summary_for_lawyer": "Intimação.",
        }
    )
    sync(baseline, movement("Intimação"))

    [draft] = _updates(drafts)
    assert draft.guardrail_flags == ["deadline"]
    assert "prazo" not in draft.generated_body
    assert "Intimação em" in draft.generated_body
    assert draft.needs_lawyer is True
    assert "prazo de 15 dias" in draft.generation.output_data["message"]


def test_permanent_llm_error_still_creates_fixed_text_draft(
    tenant_a, baseline, sync, drafts, fake_llm
):
    fake_llm.queue.append(LlmError("bad_request", retryable=False))
    sync(baseline, movement("Conclusão"))

    [draft] = _updates(drafts)
    assert draft.generation is None
    assert "Conclusão em" in draft.generated_body
    with tenant_context(tenant_a.tenant.id):
        statuses = list(AiGeneration.objects.values_list("status", flat=True))
    assert statuses == [AiGeneration.Status.ERROR]


def test_retryable_llm_error_is_raised_and_retry_does_not_duplicate(
    tenant_a, baseline, fake_source, drafts, fake_llm
):
    from dataclasses import replace

    from apps.processos import monitoring

    snapshot = fake_source.snapshots[baseline.cnj_number]
    fake_source.snapshots[baseline.cnj_number] = replace(
        snapshot, movements=(*snapshot.movements, movement("Conclusão"))
    )
    # Sem executar os on_commit: a task é chamada à mão abaixo.
    monitoring.sync_case(tenant_a.tenant.id, baseline.pk)
    fake_llm.queue.append(LlmError("overloaded", retryable=True))

    with pytest.raises(movement_service.RetryableMovementError):
        movement_service.explain_case_movements(tenant_a.tenant.id, baseline.pk)
    assert _updates(drafts) == []

    assert movement_service.explain_case_movements(tenant_a.tenant.id, baseline.pk) == "drafts:1"
    # Task repetida (acks_late, worker reiniciado) não refaz o rascunho.
    assert movement_service.explain_case_movements(tenant_a.tenant.id, baseline.pk) == (
        "nothing_to_draft"
    )
    assert len(_updates(drafts)) == 1


def test_newer_movement_supersedes_pending_draft_and_covers_both(tenant_a, baseline, sync, drafts):
    sync(baseline, movement("Conclusão", timezone.now() - timedelta(days=2)))
    sync(baseline, movement("Despacho", timezone.now() - timedelta(days=1)))

    old, new = _updates(drafts)
    assert old.status == OutboundDraft.Status.REJECTED
    assert new.status == OutboundDraft.Status.DRAFT
    by_name = _movements(tenant_a, baseline)
    assert new.movement_ids == [str(by_name["Conclusão"].pk), str(by_name["Despacho"].pk)]


def test_one_draft_per_linked_client(tenant_a, baseline, sync, drafts, fake_llm):
    with tenant_context(tenant_a.tenant.id):
        joao = Client.objects.create(name="João Souza", phone_e164="+5521977776666")
        CaseClient.objects.create(case=baseline, client=joao, role=CaseClient.Role.DEFENDANT)
        linked = set(CaseClient.objects.filter(case=baseline).values_list("client_id", flat=True))
    sync(baseline, movement("Conclusão"))

    drafts_ = _updates(drafts)
    assert len(drafts_) == 2
    assert {d.client_id for d in drafts_} == linked
    roles = sorted("Réu" in c.user_content for c in fake_llm.calls)
    assert roles == [False, True]


def test_client_without_phone_is_skipped_and_audited(tenant_a, baseline, sync, drafts):
    with tenant_context(tenant_a.tenant.id):
        Client.objects.update(phone_e164="")
    sync(baseline, movement("Conclusão"))

    assert _updates(drafts) == []
    with tenant_context(tenant_a.tenant.id):
        event = AuditEvent.objects.get(action="case.notification_skipped")
    assert event.data["reason"] == "no_whatsapp"


# --------------------------------------------------------------------------- aprovação e envio


def test_window_closed_sends_template_then_text_after_client_replies(
    tenant_a, baseline, sync, drafts, approve, fake_gateway, inbound
):
    sync(baseline, movement("Conclusão"))
    [draft] = _updates(drafts)

    approved = approve(draft, body="Olá, Maria! Seu processo foi para o juiz analisar.")

    assert approved.status == OutboundDraft.Status.AWAITING
    [template] = fake_gateway.sent
    assert template.to == MARIA_WA
    assert template.template == "atualizacao_processo"
    assert template.params == ["Maria", baseline.cnj_formatted]
    assert _movements(tenant_a, baseline)["Conclusão"].notification == "NOTIFIED"
    with tenant_context(tenant_a.tenant.id):
        message = Message.objects.get(type=Message.Type.TEMPLATE)
    assert baseline.cnj_formatted in message.body  # prévia para o inbox

    inbound("Oi! Pode falar", wa_id=MARIA_WA)

    [draft] = _updates(drafts)
    assert draft.status == OutboundDraft.Status.SENT
    assert fake_gateway.sent[1].body == "Olá, Maria! Seu processo foi para o juiz analisar."
    with tenant_context(tenant_a.tenant.id):
        actions = list(
            AuditEvent.objects.filter(entity_id=draft.pk)
            .order_by("created_at")
            .values_list("action", flat=True)
        )
    assert actions == [
        "draft.created",
        "draft.approved",
        "draft.template_sent",
        "draft.followup_queued",
        "draft.sent",
    ]


def test_window_open_sends_text_directly(
    tenant_a, baseline, sync, drafts, approve, fake_gateway, inbound
):
    inbound("Bom dia, alguma novidade?", wa_id=MARIA_WA)
    sync(baseline, movement("Conclusão"))
    [draft] = _updates(drafts)

    approve(draft)

    [draft] = _updates(drafts)
    assert draft.status == OutboundDraft.Status.SENT
    sent = fake_gateway.sent[-1]  # antes dele, só o termo de IA
    assert sent.template == ""
    assert sent.body == draft.generated_body


def test_failed_template_marks_draft_failed(
    tenant_a, baseline, sync, drafts, approve, post_webhook
):
    sync(baseline, movement("Conclusão"))
    [draft] = _updates(drafts)
    approve(draft)
    with tenant_context(tenant_a.tenant.id):
        wamid = Message.objects.get(type=Message.Type.TEMPLATE).wa_message_id

    post_webhook(status_payload(NUMBER_A, wamid, "failed"))

    [draft] = _updates(drafts)
    assert draft.status == OutboundDraft.Status.FAILED


def test_template_not_configured_keeps_draft_pending(tenant_a, baseline, sync, drafts, approve):
    with tenant_context(tenant_a.tenant.id):
        WhatsAppAccount.objects.update(movement_template_name="")
    sync(baseline, movement("Conclusão"))
    [draft] = _updates(drafts)

    from apps.core.exceptions import ApiError

    with pytest.raises(ApiError) as exc:
        approve(draft)
    assert exc.value.error_code == "template_not_configured"
    assert _updates(drafts)[0].status == OutboundDraft.Status.DRAFT


def test_reject_marks_movements_skipped(tenant_a, baseline, sync, drafts):
    sync(baseline, movement("Conclusão"))
    [draft] = _updates(drafts)
    with tenant_context(tenant_a.tenant.id):
        reject_draft(draft=draft, user=tenant_a.owner, membership=tenant_a.membership)
    assert _movements(tenant_a, baseline)["Conclusão"].notification == "SKIPPED"


def test_draft_api_shows_case_and_movements(
    tenant_a, baseline, sync, drafts, approve, login, api_client
):
    sync(baseline, movement("Conclusão"))
    [draft] = _updates(drafts)
    approve(draft)
    login(tenant_a.owner.email)

    [item] = api_client.get("/api/v1/drafts/?status=AWAITING").json()["results"]
    assert item["case_number"] == baseline.cnj_formatted
    assert [m["name"] for m in item["movements"]] == ["Conclusão"]
    assert item["template_status"] == "SENT"
    assert "Responda esta mensagem" in item["template_text"]


def test_reply_from_wa_id_without_ninth_digit_releases_waiting_text(
    tenant_a, baseline, sync, drafts, approve, fake_gateway, inbound
):
    """A conversa do aviso nasce com o 9; a Meta pode mandar a resposta sem ele."""
    sync(baseline, movement("Conclusão"))
    [draft] = _updates(drafts)
    approve(draft)

    inbound("Oi, pode mandar", wa_id="552198765432")

    [draft] = _updates(drafts)
    assert draft.status == OutboundDraft.Status.SENT
    assert fake_gateway.sent[-1].to == "552198765432"
    with tenant_context(tenant_a.tenant.id):
        from apps.whatsapp.models import Conversation

        assert Conversation.objects.count() == 1


def test_existing_conversation_without_ninth_digit_is_reused_for_updates(
    tenant_a, baseline, sync, drafts, inbound
):
    inbound("Bom dia", wa_id="552198765432")
    sync(baseline, movement("Conclusão"))

    [draft] = _updates(drafts)
    with tenant_context(tenant_a.tenant.id):
        from apps.whatsapp.models import Conversation

        [only] = Conversation.objects.all()
    assert only.wa_id == "552198765432"
    assert draft.conversation_id == only.pk

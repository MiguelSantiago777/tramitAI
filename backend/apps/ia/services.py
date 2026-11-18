"""Triagem de mensagens recebidas.

Três fases, como manda a regra do projeto:
1. transação curta: lê estado, decide o caminho (termo, aceite, triagem) e monta o contexto;
2. fora de transação: chama o LLM;
3. transação curta: registra a geração, aplica guardrails e cria o rascunho para aprovação.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.utils import timezone

from apps.aprovacoes import services as approvals
from apps.aprovacoes.models import OutboundDraft
from apps.cobranca.services import is_blocked
from apps.core import audit
from apps.core.tenancy import tenant_atomic
from apps.tenants.models import ClientTermVersion, TenantSettings
from apps.tenants.services import active_term_version
from apps.whatsapp.models import Conversation, Message

from . import consent
from .context import build_triage_context
from .guardrails import SAFE_REPLY, check_reply
from .llm import LlmError, LlmRefusal, LlmRequest, LlmResult, get_llm_client
from .models import AiGeneration
from .prompts import load_prompt
from .triage import TRIAGE_SCHEMA, InvalidTriage, parse_triage

logger = logging.getLogger(__name__)


class RetryableTriageError(Exception):
    pass


@dataclass(frozen=True)
class _Plan:
    request: LlmRequest
    context: str
    prompt_version: str


def handle_inbound(tenant_id: uuid.UUID, conversation_id: uuid.UUID, message_id: uuid.UUID) -> str:
    """Decide o que fazer com uma mensagem recebida. Devolve um código de resultado."""
    with tenant_atomic(tenant_id):
        outcome, plan = _prepare(conversation_id, message_id)
    if plan is None:
        logger.info("triage: conversa %s → %s", conversation_id, outcome)
        return outcome

    try:
        result = get_llm_client().complete(plan.request)
    except LlmError as exc:
        with tenant_atomic(tenant_id):
            _record_failure(conversation_id, message_id, plan, exc)
        logger.warning("triage: falha no LLM (%s) conversa %s", exc.code, conversation_id)
        if exc.retryable:
            raise RetryableTriageError(exc.code) from exc
        mark_ai_failed(tenant_id, conversation_id)
        return "llm_failed"

    with tenant_atomic(tenant_id):
        outcome = _store(conversation_id, message_id, plan, result)
    logger.info("triage: conversa %s → %s", conversation_id, outcome)
    return outcome


def mark_ai_failed(tenant_id: uuid.UUID, conversation_id: uuid.UUID) -> None:
    """A Lia desistiu desta conversa: a tela avisa a equipe para responder ou tentar de novo."""
    with tenant_atomic(tenant_id):
        Conversation.objects.filter(pk=conversation_id).update(ai_failed_at=timezone.now())


def _prepare(conversation_id: uuid.UUID, message_id: uuid.UUID) -> tuple[str, _Plan | None]:
    conversation = Conversation.objects.select_related("client").filter(pk=conversation_id).first()
    message = Message.objects.filter(pk=message_id, conversation_id=conversation_id).first()
    if conversation is None or message is None:
        return "missing", None
    if _is_superseded(conversation, message):
        return "superseded", None

    settings_ = TenantSettings.objects.first()
    if settings_ is not None and not settings_.ai_triage_enabled:
        return "ai_disabled", None
    if is_blocked(conversation.tenant_id):
        return "subscription_blocked", None  # sem assinatura, sem custo de IA

    term = active_term_version()
    if term is None:
        return "no_term", None

    if not consent.is_accepted(conversation, term):
        outcome = _handle_consent(conversation, term, message)
        if outcome != "accepted":
            return outcome, None
        conversation.refresh_from_db()

    if message.type != Message.Type.TEXT or not message.body.strip():
        return "not_text", None

    prompt = load_prompt("triage")
    context = build_triage_context(conversation)
    request = LlmRequest(
        system=prompt.text, user_content=context, json_schema=TRIAGE_SCHEMA, purpose="triage"
    )
    return "ready", _Plan(request=request, context=context, prompt_version=prompt.version)


def _handle_consent(conversation: Conversation, term: ClientTermVersion, message: Message) -> str:
    if (
        message.type == Message.Type.TEXT
        and consent.is_acceptance_text(message.body)
        and consent.offer_was_sent(conversation, term)
    ):
        consent.accept(conversation, term, message)
        return "accepted"
    if consent.offer_is_active(conversation, term):
        return "awaiting_consent"
    consent.offer(conversation, term, message)
    return "consent_offered"


def _is_superseded(conversation: Conversation, message: Message) -> bool:
    """Chegou mensagem mais nova? Então a triagem dela cobre esta (debounce)."""
    return (
        Message.objects.filter(
            conversation=conversation,
            direction=Message.Direction.INBOUND,
            created_at__gt=message.created_at,
        )
        .exclude(pk=message.pk)
        .exists()
    )


def _record_failure(
    conversation_id: uuid.UUID, message_id: uuid.UUID, plan: _Plan, exc: LlmError
) -> None:
    generation = AiGeneration.objects.create(
        kind=AiGeneration.Kind.TRIAGE,
        status=AiGeneration.Status.REFUSED
        if isinstance(exc, LlmRefusal)
        else AiGeneration.Status.ERROR,
        prompt_name="triage",
        prompt_version=plan.prompt_version,
        provider=get_llm_client().provider,
        conversation_id=conversation_id,
        trigger_message_id=message_id,
        error_code=exc.code[:64],
    )
    audit.record(
        "ai.failed",
        generation,
        actor_type=audit.Actor.AI,
        data={"error_code": exc.code, "retryable": exc.retryable},
    )


def _store(
    conversation_id: uuid.UUID, message_id: uuid.UUID, plan: _Plan, result: LlmResult
) -> str:
    conversation = Conversation.objects.select_related("client").get(pk=conversation_id)
    generation = AiGeneration.objects.create(
        kind=AiGeneration.Kind.TRIAGE,
        status=AiGeneration.Status.OK,
        prompt_name="triage",
        prompt_version=plan.prompt_version,
        provider=result.provider,
        model=result.model,
        conversation=conversation,
        trigger_message_id=message_id,
        output_text=result.raw_text,
        output_data=result.data,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        latency_ms=result.latency_ms,
        request_id=result.request_id[:128],
    )

    try:
        triage = parse_triage(result.data)
    except InvalidTriage as exc:
        generation.status = AiGeneration.Status.ERROR
        generation.error_code = "invalid_output"
        generation.save(update_fields=["status", "error_code", "updated_at"])
        audit.record(
            "ai.failed", generation, actor_type=audit.Actor.AI, data={"error_code": str(exc)}
        )
        Conversation.objects.filter(pk=conversation.pk).update(ai_failed_at=timezone.now())
        return "invalid_output"

    flags = check_reply(triage.reply, plan.context)
    generation.guardrail_flags = flags
    generation.save(update_fields=["guardrail_flags", "updated_at"])
    audit.record(
        "ai.generated",
        generation,
        actor_type=audit.Actor.AI,
        data={
            "model": result.model,
            "prompt_version": plan.prompt_version,
            "guardrail_flags": flags,
            "intent": triage.intent,
        },
    )

    message = Message.objects.get(pk=message_id)
    if _is_superseded(conversation, message):
        # Gerou, mas o cliente mandou mais coisa: a triagem da mensagem nova vale.
        return "superseded_after_generation"

    Conversation.objects.filter(pk=conversation.pk).update(ai_failed_at=None)
    auto_mode = _auto_triage_enabled() and _is_new_contact(conversation)
    booking_failed = False
    if triage.scheduling_step == "book" and not flags:
        booking_failed = not _prebook(conversation, triage)
    draft = approvals.create_draft(
        conversation=conversation,
        origin=OutboundDraft.Origin.AI_REPLY,
        body=SAFE_REPLY if flags else triage.reply,
        actor_type=audit.Actor.AI,
        generation=generation,
        source_message=message,
        intent=triage.intent,
        urgency=triage.urgency,
        needs_lawyer=triage.needs_lawyer or bool(flags) or booking_failed,
        summary=(
            "O horário escolhido não está mais livre: combine outro com o contato. "
            if booking_failed
            else ""
        )
        + triage.summary_for_lawyer,
        guardrail_flags=flags,
    )
    outcome = "draft_created"
    if (
        auto_mode
        and not booking_failed
        and _can_auto_send(conversation, triage, flags)
        and approvals.auto_send(draft)
    ):
        outcome = "auto_sent"
    elif auto_mode:
        # Triagem terminou (ou precisa do advogado): o cliente fica sabendo na hora, e o
        # rascunho da Lia espera a aprovação.
        _acknowledge_handoff(conversation)
    if triage.intent == "new_matter":
        # Pessoa querendo contratar: entra no funil de novos clientes.
        from apps.funil.services import ensure_whatsapp_opportunity

        ensure_whatsapp_opportunity(conversation, triage.summary_for_lawyer)
    return outcome


# ---------------------------------------------------------------- triagem automática

# Teto de mensagens que a Lia manda sozinha numa conversa em 24h (evita conversa em loop).
MAX_AUTO_REPLIES_PER_DAY = 8
HANDOFF_ACK = (
    "Obrigada pelas informações! Já passei tudo para o(a) advogado(a) do escritório, "
    "que vai analisar e te responder por aqui."
)


def _auto_triage_enabled() -> bool:
    settings_ = TenantSettings.objects.first()
    return bool(settings_ and settings_.auto_send_simple_replies)


def _scheduling_enabled() -> bool:
    settings_ = TenantSettings.objects.first()
    return bool(settings_ and settings_.scheduling_enabled)


def _prebook(conversation: Conversation, triage: Any) -> bool:
    """Contato escolheu um dos horários oferecidos: pré-reserva na agenda (a confirmar)."""
    from datetime import datetime

    from apps.agenda import scheduling

    cfg = TenantSettings.objects.first()
    client = conversation.client
    if cfg is None or not cfg.scheduling_enabled or client is None:
        return False
    chosen = next(
        (o for o in conversation.offered_slots if o.get("id") == triage.booking_slot), None
    )
    if chosen is None:
        return False
    booking = scheduling.prebook(
        cfg,
        client=client,
        start=datetime.fromisoformat(chosen["start"]),
        mode=triage.booking_mode,
        summary=triage.summary_for_lawyer,
    )
    if booking is not None:
        # Reservado: a próxima oferta (se houver) começa do zero.
        Conversation.objects.filter(pk=conversation.pk).update(offered_slots=[])
    return booking is not None


def _is_new_contact(conversation: Conversation) -> bool:
    """Só contato novo (sem cliente ou lead). Cliente com processo continua com aprovação."""
    from apps.clientes.models import Client

    client = conversation.client
    return client is None or client.status == Client.Status.LEAD


def _can_auto_send(conversation: Conversation, triage: Any, flags: list[str]) -> bool:
    if flags or triage.needs_lawyer or triage.urgency == "high":
        return False
    # Oferecer horários e confirmar a pré-reserva também sai sozinho: quem confirma de fato é
    # o advogado, pela agenda. Fora isso, triagem terminada vai para aprovação.
    scheduling = triage.scheduling_step in ("offer", "book") and _scheduling_enabled()
    if triage.triage_complete and not scheduling:
        return False
    since = timezone.now() - timedelta(hours=24)
    sent_today = OutboundDraft.objects.filter(
        conversation=conversation, auto_sent=True, created_at__gte=since
    ).count()
    return sent_today < MAX_AUTO_REPLIES_PER_DAY


def _acknowledge_handoff(conversation: Conversation) -> None:
    from apps.core.exceptions import ApiError
    from apps.whatsapp.services import queue_text

    last_out = (
        Message.objects.filter(conversation=conversation, direction=Message.Direction.OUTBOUND)
        .order_by("-created_at")
        .first()
    )
    if last_out is not None and last_out.body == HANDOFF_ACK:
        return  # já avisou; não repete a cada mensagem
    try:
        queue_text(conversation=conversation, body=HANDOFF_ACK, sent_by=None)
    except ApiError:
        logger.info("triage: aviso de encaminhamento não enviado (janela fechada)")

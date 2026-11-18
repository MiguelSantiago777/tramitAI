"""Triagem de mensagens recebidas.

Três fases, como manda a regra do projeto:
1. transação curta: lê estado, decide o caminho (termo, aceite, triagem) e monta o contexto;
2. fora de transação: chama o LLM;
3. transação curta: registra a geração, aplica guardrails e cria o rascunho para aprovação.
"""

import logging
import uuid
from dataclasses import dataclass

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
        return "llm_failed"

    with tenant_atomic(tenant_id):
        outcome = _store(conversation_id, message_id, plan, result)
    logger.info("triage: conversa %s → %s", conversation_id, outcome)
    return outcome


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

    approvals.create_draft(
        conversation=conversation,
        origin=OutboundDraft.Origin.AI_REPLY,
        body=SAFE_REPLY if flags else triage.reply,
        actor_type=audit.Actor.AI,
        generation=generation,
        source_message=message,
        intent=triage.intent,
        urgency=triage.urgency,
        needs_lawyer=triage.needs_lawyer or bool(flags),
        summary=triage.summary_for_lawyer,
        guardrail_flags=flags,
    )
    if triage.intent == "new_matter":
        # Pessoa querendo contratar: entra no funil de novos clientes.
        from apps.funil.services import ensure_whatsapp_opportunity

        ensure_whatsapp_opportunity(conversation, triage.summary_for_lawyer)
    return "draft_created"

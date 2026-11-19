"""Aviso de andamento em português simples.

Andamentos novos (PENDING) de um processo viram um rascunho por cliente vinculado, para o
advogado aprovar. Três fases, como na triagem: prepara numa transação curta, chama o LLM fora
de transação e grava numa transação curta.

Entra no LLM só o que é público no tribunal (número, classe, assunto, órgão, nomes dos
andamentos) e o papel do cliente no processo. Nome, CPF e telefone do cliente não entram: a
saudação é montada aqui. Se a IA estiver desligada, falhar ou violar um guardrail, o rascunho
usa um texto fixo montado só com os dados do tribunal.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from apps.aprovacoes import services as approvals
from apps.aprovacoes.models import OutboundDraft
from apps.clientes.models import Client
from apps.core import audit
from apps.core.tenancy import tenant_atomic
from apps.processos.models import CaseClient, CaseMovement, LegalCase
from apps.tenants.models import TenantSettings
from apps.whatsapp import services as whatsapp
from apps.whatsapp.models import Conversation

from .context import _clean, _day
from .guardrails import check_reply
from .llm import LlmError, LlmRefusal, LlmRequest, LlmResult, get_llm_client
from .models import AiGeneration
from .prompts import load_prompt

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 1200
MAX_MOVEMENTS_IN_CONTEXT = 15
PREVIOUS_MOVEMENTS = 5

MOVEMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "message": {"type": "string"},
        "client_relevant": {"type": "boolean"},
        "needs_lawyer": {"type": "boolean"},
        "summary_for_lawyer": {"type": "string"},
    },
    "required": ["message", "client_relevant", "needs_lawyer", "summary_for_lawyer"],
    "additionalProperties": False,
}


class RetryableMovementError(Exception):
    pass


class InvalidMovementUpdate(ValueError):
    pass


@dataclass(frozen=True)
class MovementUpdate:
    message: str
    client_relevant: bool
    needs_lawyer: bool
    summary_for_lawyer: str


def parse_movement_update(data: dict[str, Any]) -> MovementUpdate:
    try:
        message = str(data["message"]).strip()
        relevant, needs_lawyer = data["client_relevant"], data["needs_lawyer"]
        summary = str(data["summary_for_lawyer"]).strip()
    except (KeyError, TypeError) as exc:
        raise InvalidMovementUpdate("campos ausentes") from exc
    if not isinstance(relevant, bool) or not isinstance(needs_lawyer, bool):
        raise InvalidMovementUpdate("booleanos inválidos")
    if not message:
        raise InvalidMovementUpdate("mensagem vazia")
    return MovementUpdate(
        message=message[:MAX_MESSAGE_LENGTH],
        client_relevant=relevant,
        needs_lawyer=needs_lawyer,
        summary_for_lawyer=summary[:1000],
    )


@dataclass(frozen=True)
class _Plan:
    client_id: uuid.UUID
    conversation_id: uuid.UUID
    first_name: str
    movement_ids: list[str]
    context: str
    fallback: str
    request: LlmRequest | None
    prompt_version: str


def explain_case_movements(tenant_id: uuid.UUID, case_id: uuid.UUID) -> str:
    """Cria os rascunhos de aviso dos andamentos pendentes. Devolve um código de resultado."""
    with tenant_atomic(tenant_id):
        outcome, plans = _prepare(case_id)
    if not plans:
        logger.info("movements: processo %s → %s", case_id, outcome)
        return outcome

    for plan in plans:
        result: LlmResult | None = None
        if plan.request is not None:
            try:
                result = get_llm_client().complete(plan.request)
            except LlmError as exc:
                with tenant_atomic(tenant_id):
                    _record_failure(case_id, plan, exc)
                logger.warning("movements: falha no LLM (%s) processo %s", exc.code, case_id)
                if exc.retryable:
                    # Rascunhos já criados neste ciclo não são refeitos (ver _prepare).
                    raise RetryableMovementError(exc.code) from exc
        with tenant_atomic(tenant_id):
            _store(case_id, plan, result)
    logger.info("movements: processo %s → %s rascunhos", case_id, len(plans))
    return f"drafts:{len(plans)}"


def _prepare(case_id: uuid.UUID) -> tuple[str, list[_Plan]]:
    case = LegalCase.objects.filter(pk=case_id).first()
    if case is None:
        return "missing", []
    pending = list(
        CaseMovement.objects.filter(
            case=case, notification=CaseMovement.Notification.PENDING
        ).order_by("occurred_at")
    )
    if not pending:
        return "nothing_pending", []
    links = list(
        CaseClient.objects.filter(case=case)
        .exclude(client__status=Client.Status.ARCHIVED)
        .select_related("client")
    )
    if not links:
        return "no_clients", []

    settings_ = TenantSettings.objects.first()
    from apps.cobranca.limits import ai_allowed

    # Limite do plano esgotado: aviso com o texto fixo (sem IA), como com a Vera desligada.
    ai_enabled = (settings_ is None or settings_.ai_triage_enabled) and ai_allowed(case.tenant_id)
    previous = list(
        CaseMovement.objects.filter(case=case)
        .exclude(notification=CaseMovement.Notification.PENDING)
        .order_by("-occurred_at")[:PREVIOUS_MOVEMENTS]
    )
    prompt = load_prompt("movement_update")
    pending_ids = {str(m.pk) for m in pending}

    plans: list[_Plan] = []
    for link in links:
        conversation = whatsapp.conversation_for_client(link.client)
        if conversation is None:
            audit.record(
                "case.notification_skipped",
                case,
                actor_type=audit.Actor.SYSTEM,
                data={"client_id": str(link.client_id), "reason": "no_whatsapp"},
            )
            continue
        movements = list(pending)
        existing = approvals.pending_movement_draft(conversation, case)
        if existing is not None:
            if pending_ids <= set(existing.movement_ids):
                continue  # já existe rascunho cobrindo tudo (task repetida)
            # O rascunho novo substitui o pendente: precisa cobrir o que ele cobria.
            carry = set(existing.movement_ids) - pending_ids
            movements += list(CaseMovement.objects.filter(pk__in=carry))
            movements.sort(key=lambda m: m.occurred_at)
        movements = movements[-MAX_MOVEMENTS_IN_CONTEXT:]

        context = build_movement_context(case, link, movements, previous)
        plans.append(
            _Plan(
                client_id=link.client_id,
                conversation_id=conversation.pk,
                first_name=(link.client.name or "").split(" ")[0],
                movement_ids=[str(m.pk) for m in movements],
                context=context,
                fallback=fallback_text(case, movements),
                request=LlmRequest(
                    system=prompt.text,
                    user_content=context,
                    json_schema=MOVEMENT_SCHEMA,
                    purpose="movement_update",
                )
                if ai_enabled
                else None,
                prompt_version=prompt.version,
            )
        )
    return ("ready" if plans else "nothing_to_draft"), plans


def _movement_line(movement: CaseMovement) -> str:
    line = f"- {_day(movement.occurred_at)}: {_clean(movement.name)}"
    if movement.complements:
        line += f" ({'; '.join(_clean(str(c)) for c in movement.complements[:5])})"
    return line


def build_movement_context(
    case: LegalCase,
    link: CaseClient,
    movements: list[CaseMovement],
    previous: list[CaseMovement],
) -> str:
    info = " | ".join(
        [
            f"número: {case.cnj_formatted}",
            f"tribunal: {case.tribunal_label or 'não identificado'}",
            f"classe: {_clean(case.classe) or 'não informada'}",
            f"assunto: {_clean(case.assunto) or 'não informado'}",
            f"órgão julgador: {_clean(case.orgao_julgador) or 'não informado'}",
            f"papel do cliente: {link.get_role_display()}",
        ]
    )
    new = "\n".join(_movement_line(m) for m in movements)
    old = "\n".join(_movement_line(m) for m in reversed(previous)) or "Nenhum."
    return (
        f"<processo>{info}</processo>\n"
        f"<andamentos_novos>\n{new}\n</andamentos_novos>\n"
        f"<andamentos_anteriores>\n{old}\n</andamentos_anteriores>"
    )


def fallback_text(case: LegalCase, movements: list[CaseMovement]) -> str:
    """Texto fixo, só com dados do tribunal (não tem como inventar nada)."""
    items = "; ".join(f"{m.name} em {_day(m.occurred_at)}" for m in movements[-5:])
    what = "uma nova movimentação" if len(movements) == 1 else "novas movimentações"
    return (
        f"Seu processo nº {case.cnj_formatted} teve {what} no tribunal: {items}. "
        "O(a) advogado(a) responsável já está acompanhando e vai te explicar se houver algo "
        "a fazer. Se tiver dúvida, é só responder esta mensagem."
    )


def _greeting(first_name: str) -> str:
    return f"Olá, {first_name}! " if first_name else "Olá! "


def _record_failure(case_id: uuid.UUID, plan: _Plan, exc: LlmError) -> None:
    generation = AiGeneration.objects.create(
        kind=AiGeneration.Kind.MOVEMENT_UPDATE,
        status=AiGeneration.Status.REFUSED
        if isinstance(exc, LlmRefusal)
        else AiGeneration.Status.ERROR,
        prompt_name="movement_update",
        prompt_version=plan.prompt_version,
        provider=get_llm_client().provider,
        conversation_id=plan.conversation_id,
        legal_case_id=case_id,
        error_code=exc.code[:64],
    )
    audit.record(
        "ai.failed",
        generation,
        actor_type=audit.Actor.AI,
        data={"error_code": exc.code, "retryable": exc.retryable},
    )


def _store(case_id: uuid.UUID, plan: _Plan, result: LlmResult | None) -> OutboundDraft | None:
    case = LegalCase.objects.get(pk=case_id)
    conversation = Conversation.objects.select_related("client").get(pk=plan.conversation_id)
    still_pending = set(
        str(pk)
        for pk in CaseMovement.objects.filter(
            pk__in=plan.movement_ids, notification=CaseMovement.Notification.PENDING
        ).values_list("pk", flat=True)
    )
    if not still_pending:
        return None  # o advogado já decidiu sobre esses andamentos enquanto a IA escrevia

    generation: AiGeneration | None = None
    update: MovementUpdate | None = None
    flags: list[str] = []
    if result is not None:
        generation = AiGeneration.objects.create(
            kind=AiGeneration.Kind.MOVEMENT_UPDATE,
            status=AiGeneration.Status.OK,
            prompt_name="movement_update",
            prompt_version=plan.prompt_version,
            provider=result.provider,
            model=result.model,
            conversation=conversation,
            legal_case=case,
            output_text=result.raw_text,
            output_data=result.data,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_ms=result.latency_ms,
            request_id=result.request_id[:128],
        )
        try:
            update = parse_movement_update(result.data)
        except InvalidMovementUpdate as exc:
            generation.status = AiGeneration.Status.ERROR
            generation.error_code = "invalid_output"
            generation.save(update_fields=["status", "error_code", "updated_at"])
            audit.record(
                "ai.failed", generation, actor_type=audit.Actor.AI, data={"error_code": str(exc)}
            )
        else:
            flags = check_reply(update.message, plan.context)
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
                    "purpose": "movement_update",
                },
            )

    use_ai_text = update is not None and not flags
    text = update.message if update is not None and use_ai_text else plan.fallback
    names = ", ".join(
        CaseMovement.objects.filter(pk__in=plan.movement_ids)
        .order_by("occurred_at")
        .values_list("name", flat=True)
    )
    return approvals.create_draft(
        conversation=conversation,
        origin=OutboundDraft.Origin.MOVEMENT_UPDATE,
        body=_greeting(plan.first_name) + text,
        actor_type=audit.Actor.AI if use_ai_text else audit.Actor.SYSTEM,
        generation=generation,
        client_id=plan.client_id,
        legal_case=case,
        movement_ids=plan.movement_ids,
        intent="case_status",
        urgency="normal",
        needs_lawyer=update is None or update.needs_lawyer or bool(flags),
        client_relevant=update.client_relevant if update is not None else None,
        summary=(update.summary_for_lawyer if update is not None else "")
        or f"Andamentos novos no processo {case.cnj_formatted}: {names}.",
        guardrail_flags=flags,
    )

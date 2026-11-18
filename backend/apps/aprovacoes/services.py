"""Fila de aprovação. A IA nunca envia sozinha: todo envio passa por approve_draft()."""

from typing import Any

from django.utils import timezone
from rest_framework import status as http_status

from apps.accounts.models import Membership, User
from apps.accounts.services import can_approve_drafts
from apps.core import audit
from apps.core.exceptions import ApiError
from apps.processos.models import CaseMovement, LegalCase
from apps.whatsapp import services as whatsapp
from apps.whatsapp.models import Conversation, Message
from apps.whatsapp.templates import MOVEMENT_UPDATE

from .models import OutboundDraft

SUPERSEDED_REASON = "Substituído por um rascunho mais recente."
# Origens em que um rascunho novo substitui o pendente (o novo cobre o anterior).
_SUPERSEDABLE = (OutboundDraft.Origin.AI_REPLY, OutboundDraft.Origin.MOVEMENT_UPDATE)


def create_draft(
    *,
    conversation: Conversation,
    origin: str,
    body: str,
    actor_type: str,
    **fields: Any,
) -> OutboundDraft:
    """Cria um rascunho. Pendentes da mesma origem (e do mesmo processo) ficam obsoletos."""
    if origin in _SUPERSEDABLE:
        _supersede_pending(conversation, origin, fields.get("legal_case"))
    if "client" not in fields and "client_id" not in fields:
        fields["client"] = conversation.client
    draft = OutboundDraft.objects.create(
        conversation=conversation,
        origin=origin,
        generated_body=body,
        **fields,
    )
    audit.record(
        "draft.created",
        draft,
        actor_type=actor_type,
        data={
            "origin": origin,
            "conversation_id": str(conversation.pk),
            "generation_id": str(draft.generation_id) if draft.generation_id else None,
            "legal_case_id": str(draft.legal_case_id) if draft.legal_case_id else None,
            "movement_count": len(draft.movement_ids),
            "guardrail_flags": draft.guardrail_flags,
        },
    )
    return draft


def pending_movement_draft(conversation: Conversation, case: LegalCase) -> OutboundDraft | None:
    return OutboundDraft.objects.filter(
        conversation=conversation,
        origin=OutboundDraft.Origin.MOVEMENT_UPDATE,
        legal_case=case,
        status=OutboundDraft.Status.DRAFT,
    ).first()


def _supersede_pending(conversation: Conversation, origin: str, case: LegalCase | None) -> None:
    pending = OutboundDraft.objects.filter(
        conversation=conversation, origin=origin, status=OutboundDraft.Status.DRAFT
    )
    if origin == OutboundDraft.Origin.MOVEMENT_UPDATE:
        pending = pending.filter(legal_case=case)
    for draft in pending:
        draft.status = OutboundDraft.Status.REJECTED
        draft.rejection_reason = SUPERSEDED_REASON
        draft.decided_at = timezone.now()
        draft.save(update_fields=["status", "rejection_reason", "decided_at", "updated_at"])
        audit.record(
            "draft.superseded", draft, actor_type=audit.Actor.SYSTEM, data={"origin": origin}
        )


def _ensure_can_decide(membership: Membership) -> None:
    if not can_approve_drafts(membership):
        raise ApiError(
            "Você não tem permissão para aprovar ou rejeitar mensagens.",
            code="permission_denied",
            status_code=http_status.HTTP_403_FORBIDDEN,
        )


def _lock_pending(draft_id: Any) -> OutboundDraft:
    draft = (
        OutboundDraft.objects.select_for_update(of=("self",))
        .select_related("conversation__account", "client", "legal_case")
        .get(pk=draft_id)
    )
    if draft.status != OutboundDraft.Status.DRAFT:
        raise ApiError(
            "Este rascunho já foi decidido.",
            code="draft_already_decided",
            status_code=http_status.HTTP_409_CONFLICT,
        )
    return draft


def auto_send(draft: OutboundDraft) -> bool:
    """Lia envia o rascunho sem aprovação (só na triagem de contato novo). Se não der para
    enviar agora (ex.: janela da Meta fechada), o rascunho fica pendente para a equipe."""
    try:
        message = whatsapp.queue_text(
            conversation=draft.conversation, body=draft.generated_body, sent_by=None
        )
    except ApiError:
        return False
    draft.status = OutboundDraft.Status.APPROVED
    draft.final_body = draft.generated_body
    draft.decided_at = timezone.now()
    draft.sent_message = message
    draft.auto_sent = True
    draft.save(
        update_fields=[
            "status",
            "final_body",
            "decided_at",
            "sent_message",
            "auto_sent",
            "updated_at",
        ]
    )
    audit.record(
        "draft.auto_sent",
        draft,
        actor_type=audit.Actor.AI,
        data={"message_id": str(message.pk), "intent": draft.intent},
    )
    return True


def approve_draft(
    *, draft: OutboundDraft, user: User, membership: Membership, body: str | None = None
) -> OutboundDraft:
    """Aprova (com edição opcional) e coloca na fila de envio do WhatsApp.

    Aviso de andamento com a janela de 24h fechada: sai o modelo aprovado pela Meta agora e o
    texto aprovado fica guardado até o cliente responder (AWAITING).
    """
    _ensure_can_decide(membership)
    draft = _lock_pending(draft.pk)
    final_body = (body if body is not None else draft.generated_body).strip()
    conversation = draft.conversation

    use_template = draft.origin == OutboundDraft.Origin.MOVEMENT_UPDATE and not (
        whatsapp.window_open(conversation)
    )
    if use_template:
        if not final_body:
            raise ApiError("Escreva a mensagem.", code="empty_message")
        if len(final_body) > whatsapp.MAX_TEXT_LENGTH:
            raise ApiError("Mensagem longa demais.", code="message_too_long")
        message = whatsapp.queue_template(
            conversation=conversation,
            spec=MOVEMENT_UPDATE,
            params=[_first_name(draft), _case_number(draft)],
            sent_by=user,
        )
        draft.status = OutboundDraft.Status.AWAITING
        draft.template_message = message
    else:
        # Valida janela de 24h e tamanho; se falhar, o rascunho continua pendente.
        message = whatsapp.queue_text(conversation=conversation, body=final_body, sent_by=user)
        draft.status = OutboundDraft.Status.APPROVED
        draft.sent_message = message

    draft.final_body = final_body
    draft.decided_by = user
    draft.decided_at = timezone.now()
    draft.save(
        update_fields=[
            "status",
            "final_body",
            "decided_by",
            "decided_at",
            "sent_message",
            "template_message",
            "updated_at",
        ]
    )
    if draft.origin == OutboundDraft.Origin.MOVEMENT_UPDATE:
        _set_movements(draft, CaseMovement.Notification.NOTIFIED)
    audit.record(
        "draft.approved",
        draft,
        actor_type=audit.Actor.USER,
        actor_user=user,
        data={
            "edited": final_body != draft.generated_body.strip(),
            "message_id": str(message.pk),
            "origin": draft.origin,
            "delivery": "template" if use_template else "text",
        },
    )
    return draft


def _first_name(draft: OutboundDraft) -> str:
    name = draft.client.name if draft.client else draft.conversation.contact_name
    return (name or "").split(" ")[0] or "tudo bem"


def _case_number(draft: OutboundDraft) -> str:
    return draft.legal_case.cnj_formatted if draft.legal_case else ""


def reject_draft(
    *, draft: OutboundDraft, user: User, membership: Membership, reason: str = ""
) -> OutboundDraft:
    _ensure_can_decide(membership)
    draft = _lock_pending(draft.pk)
    draft.status = OutboundDraft.Status.REJECTED
    draft.rejection_reason = reason.strip()[:255]
    draft.decided_by = user
    draft.decided_at = timezone.now()
    draft.save(
        update_fields=["status", "rejection_reason", "decided_by", "decided_at", "updated_at"]
    )
    if draft.origin == OutboundDraft.Origin.MOVEMENT_UPDATE:
        _skip_movements_without_pending_draft(draft)
    audit.record(
        "draft.rejected",
        draft,
        actor_type=audit.Actor.USER,
        actor_user=user,
        data={"origin": draft.origin, "has_reason": bool(draft.rejection_reason)},
    )
    return draft


def _set_movements(draft: OutboundDraft, notification: str) -> None:
    CaseMovement.objects.filter(
        pk__in=draft.movement_ids,
        notification__in=[CaseMovement.Notification.PENDING, CaseMovement.Notification.SKIPPED],
    ).update(notification=notification)


def _skip_movements_without_pending_draft(draft: OutboundDraft) -> None:
    """Rejeitado: andamentos que não estão em outro rascunho pendente ficam "sem aviso"."""
    still_pending: set[str] = set()
    others = OutboundDraft.objects.filter(
        legal_case_id=draft.legal_case_id,
        origin=OutboundDraft.Origin.MOVEMENT_UPDATE,
        status=OutboundDraft.Status.DRAFT,
    ).exclude(pk=draft.pk)
    for movement_ids in others.values_list("movement_ids", flat=True):
        still_pending.update(movement_ids)
    CaseMovement.objects.filter(
        pk__in=[m for m in draft.movement_ids if m not in still_pending],
        notification=CaseMovement.Notification.PENDING,
    ).update(notification=CaseMovement.Notification.SKIPPED)


def on_inbound_message(conversation: Conversation) -> None:
    """Sinal do WhatsApp: o cliente escreveu, a janela abriu. Sai o texto que o advogado já
    aprovou e estava esperando (aviso de andamento enviado antes por modelo)."""
    waiting = OutboundDraft.objects.select_for_update(of=("self",)).filter(
        conversation=conversation, status=OutboundDraft.Status.AWAITING
    )
    for draft in waiting.select_related("decided_by").order_by("created_at"):
        try:
            message = whatsapp.queue_text(
                conversation=conversation, body=draft.final_body, sent_by=draft.decided_by
            )
        except ApiError as exc:
            draft.status = OutboundDraft.Status.FAILED
            draft.failure_detail = str(exc.detail)[:255]
            draft.save(update_fields=["status", "failure_detail", "updated_at"])
            audit.record(
                "draft.failed",
                draft,
                actor_type=audit.Actor.SYSTEM,
                data={"error_code": exc.error_code},
            )
            continue
        draft.status = OutboundDraft.Status.APPROVED
        draft.sent_message = message
        draft.save(update_fields=["status", "sent_message", "updated_at"])
        audit.record(
            "draft.followup_queued",
            draft,
            actor_type=audit.Actor.SYSTEM,
            data={"message_id": str(message.pk)},
        )


def on_message_settled(message: Message) -> None:
    """Sinal do WhatsApp: mensagem do rascunho saiu (SENT) ou falhou (FAILED)."""
    template_draft = OutboundDraft.objects.filter(template_message=message).first()
    if template_draft is not None:
        _on_template_settled(template_draft, message)
        return

    draft = OutboundDraft.objects.filter(sent_message=message).first()
    if draft is None:
        return
    if message.status == Message.Status.SENT and draft.status == OutboundDraft.Status.APPROVED:
        draft.status = OutboundDraft.Status.SENT
        draft.save(update_fields=["status", "updated_at"])
        audit.record(
            "draft.sent",
            draft,
            actor_type=audit.Actor.SYSTEM,
            data={"message_id": str(message.pk), "wa_message_id": message.wa_message_id},
        )
    elif message.status == Message.Status.FAILED and draft.status in (
        OutboundDraft.Status.APPROVED,
        OutboundDraft.Status.SENT,
    ):
        _fail(draft, message)


def _on_template_settled(draft: OutboundDraft, message: Message) -> None:
    if message.status == Message.Status.SENT and draft.status == OutboundDraft.Status.AWAITING:
        audit.record(
            "draft.template_sent",
            draft,
            actor_type=audit.Actor.SYSTEM,
            data={"message_id": str(message.pk), "wa_message_id": message.wa_message_id},
        )
    elif message.status == Message.Status.FAILED and draft.status == OutboundDraft.Status.AWAITING:
        _fail(draft, message)


def _fail(draft: OutboundDraft, message: Message) -> None:
    draft.status = OutboundDraft.Status.FAILED
    draft.failure_detail = message.error_detail
    draft.save(update_fields=["status", "failure_detail", "updated_at"])
    audit.record(
        "draft.failed",
        draft,
        actor_type=audit.Actor.SYSTEM,
        data={"message_id": str(message.pk), "error_code": message.error_code},
    )

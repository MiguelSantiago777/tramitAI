"""Fila de aprovação. A IA nunca envia sozinha: todo envio passa por approve_draft()."""

from typing import Any

from django.utils import timezone
from rest_framework import status as http_status

from apps.accounts.models import Membership, User
from apps.accounts.services import can_approve_drafts
from apps.core import audit
from apps.core.exceptions import ApiError
from apps.whatsapp import services as whatsapp
from apps.whatsapp.models import Conversation, Message

from .models import OutboundDraft

SUPERSEDED_REASON = "Substituído por um rascunho mais recente."


def create_draft(
    *,
    conversation: Conversation,
    origin: str,
    body: str,
    actor_type: str,
    **fields: Any,
) -> OutboundDraft:
    """Cria um rascunho. Rascunhos pendentes da mesma origem na conversa ficam obsoletos."""
    if origin == OutboundDraft.Origin.AI_REPLY:
        _supersede_pending(conversation, origin)
    draft = OutboundDraft.objects.create(
        conversation=conversation,
        client=conversation.client,
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
            "guardrail_flags": draft.guardrail_flags,
        },
    )
    return draft


def _supersede_pending(conversation: Conversation, origin: str) -> None:
    pending = OutboundDraft.objects.filter(
        conversation=conversation, origin=origin, status=OutboundDraft.Status.DRAFT
    )
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
        OutboundDraft.objects.select_for_update().select_related("conversation").get(pk=draft_id)
    )
    if draft.status != OutboundDraft.Status.DRAFT:
        raise ApiError(
            "Este rascunho já foi decidido.",
            code="draft_already_decided",
            status_code=http_status.HTTP_409_CONFLICT,
        )
    return draft


def approve_draft(
    *, draft: OutboundDraft, user: User, membership: Membership, body: str | None = None
) -> OutboundDraft:
    """Aprova (com edição opcional) e coloca na fila de envio do WhatsApp."""
    _ensure_can_decide(membership)
    draft = _lock_pending(draft.pk)
    final_body = (body if body is not None else draft.generated_body).strip()

    # Valida janela de 24h e tamanho; se falhar, o rascunho continua pendente.
    message = whatsapp.queue_text(conversation=draft.conversation, body=final_body, sent_by=user)

    draft.status = OutboundDraft.Status.APPROVED
    draft.final_body = final_body
    draft.decided_by = user
    draft.decided_at = timezone.now()
    draft.sent_message = message
    draft.save(
        update_fields=[
            "status",
            "final_body",
            "decided_by",
            "decided_at",
            "sent_message",
            "updated_at",
        ]
    )
    audit.record(
        "draft.approved",
        draft,
        actor_type=audit.Actor.USER,
        actor_user=user,
        data={
            "edited": final_body != draft.generated_body.strip(),
            "message_id": str(message.pk),
            "origin": draft.origin,
        },
    )
    return draft


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
    audit.record(
        "draft.rejected",
        draft,
        actor_type=audit.Actor.USER,
        actor_user=user,
        data={"origin": draft.origin, "has_reason": bool(draft.rejection_reason)},
    )
    return draft


def on_message_settled(message: Message) -> None:
    """Sinal do WhatsApp: a mensagem do rascunho saiu (SENT) ou falhou (FAILED)."""
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
        draft.status = OutboundDraft.Status.FAILED
        draft.failure_detail = message.error_detail
        draft.save(update_fields=["status", "failure_detail", "updated_at"])
        audit.record(
            "draft.failed",
            draft,
            actor_type=audit.Actor.SYSTEM,
            data={"message_id": str(message.pk), "error_code": message.error_code},
        )

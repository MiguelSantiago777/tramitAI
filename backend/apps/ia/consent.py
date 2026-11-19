"""Termo de ciência de IA dentro da conversa.

Regra: nenhuma mensagem do contato vai para o provedor de IA antes do aceite da versão vigente
do termo. Até lá, o sistema só oferece o termo: texto fixo, sem IA, enviado sozinho (se a janela
da Meta estiver fechada, fica como rascunho para a equipe enviar).
"""

import re
import unicodedata

from django.utils import timezone

from apps.aprovacoes import services as approvals
from apps.aprovacoes.models import OutboundDraft
from apps.clientes.models import Client, ClientTermAcceptance
from apps.clientes.services import register_term_acceptance
from apps.core import audit
from apps.core.br import normalize_br_phone, whatsapp_phone_candidates
from apps.tenants.models import ClientTermVersion, Tenant
from apps.whatsapp.models import Conversation, Message

from .prompts import load_prompt

_ACCEPT = re.compile(
    r"^(?:(?:sim|ok|certo|tudo bem|pode ser)\s+)?(?:eu\s+)?aceito"
    r"(?:\s+(?:sim|o termo|obrigad[oa]|obg))?$"
)

OFFER_ACTIVE_STATUSES = (
    OutboundDraft.Status.DRAFT,
    OutboundDraft.Status.APPROVED,
    OutboundDraft.Status.SENT,
)


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", plain).split())


def is_acceptance_text(text: str) -> bool:
    return bool(_ACCEPT.match(_normalize(text or "")))


def is_accepted(conversation: Conversation, term: ClientTermVersion) -> bool:
    if conversation.client_id is None:
        return False
    return ClientTermAcceptance.objects.filter(
        client_id=conversation.client_id, term_version=term
    ).exists()


def offer_is_active(conversation: Conversation, term: ClientTermVersion) -> bool:
    """Já existe oferta do termo vigente nesta conversa (pendente, aprovada ou enviada)?"""
    return OutboundDraft.objects.filter(
        conversation=conversation,
        origin=OutboundDraft.Origin.TERM_REQUEST,
        term_version=term,
        status__in=OFFER_ACTIVE_STATUSES,
    ).exists()


def offer_was_sent(conversation: Conversation, term: ClientTermVersion) -> bool:
    return OutboundDraft.objects.filter(
        conversation=conversation,
        origin=OutboundDraft.Origin.TERM_REQUEST,
        term_version=term,
        status=OutboundDraft.Status.SENT,
    ).exists()


def offer(conversation: Conversation, term: ClientTermVersion, trigger: Message) -> OutboundDraft:
    """Envia o termo (sem IA). Se não der para enviar agora, fica o rascunho para a equipe."""
    tenant = Tenant.objects.get(pk=conversation.tenant_id)
    name = conversation.client.name if conversation.client else conversation.contact_name
    first_name = (name or "").split(" ")[0]
    body = load_prompt("term_request").text.format(
        saudacao=f", {first_name}" if first_name else "",
        escritorio=tenant.name,
        termo=term.body,
    )
    Conversation.objects.filter(pk=conversation.pk).update(ai_consent_version=term.version)
    draft = approvals.create_draft(
        conversation=conversation,
        origin=OutboundDraft.Origin.TERM_REQUEST,
        body=body,
        actor_type=audit.Actor.SYSTEM,
        term_version=term,
        source_message=trigger,
        summary="Primeiro contato: enviar o termo de ciência de uso de IA.",
    )
    # O texto é o termo publicado pelo próprio escritório (sem IA): não há o que revisar.
    approvals.auto_send(draft)
    return draft


def _lead_phone(wa_id: str) -> str:
    for candidate in whatsapp_phone_candidates(wa_id):
        normalized = normalize_br_phone(candidate)
        if normalized:
            return normalized
    return f"+{wa_id}"


def accept(conversation: Conversation, term: ClientTermVersion, message: Message) -> Client:
    """Registra o aceite feito pelo WhatsApp. Sem cliente vinculado, cria um LEAD."""
    client = conversation.client
    if client is None:
        client = Client.objects.create(
            kind=Client.Kind.PERSON,
            name=conversation.contact_name or "Contato do WhatsApp",
            phone_e164=_lead_phone(conversation.wa_id),
            status=Client.Status.LEAD,
            notes="Lead criado automaticamente após aceite do termo pelo WhatsApp.",
        )
        audit.record(
            "client.lead_created",
            client,
            actor_type=audit.Actor.SYSTEM,
            data={"conversation_id": str(conversation.pk)},
        )
        Conversation.objects.filter(pk=conversation.pk).update(client=client)
        conversation.client = client

    acceptance = register_term_acceptance(
        client=client,
        channel=ClientTermAcceptance.Channel.WHATSAPP,
        accepted_at=message.wa_timestamp or timezone.now(),
        evidence=f"WhatsApp {message.wa_message_id}",
    )
    audit.record(
        "term.accepted",
        acceptance,
        actor_type=audit.Actor.SYSTEM,
        data={
            "conversation_id": str(conversation.pk),
            "term_version": term.version,
            "message_id": str(message.pk),
        },
    )
    return client

"""Monta o contexto da triagem a partir do banco (tenant ativo).

Só entra o que é necessário: dados do cliente vinculado e dos processos dele, e as últimas
mensagens. Cliente só sugerido (por CPF) NÃO entra: CPF digitado não prova identidade.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings

from apps.processos.models import LegalCase
from apps.tenants.models import Tenant
from apps.whatsapp.models import Conversation, Message

TZ = ZoneInfo(settings.TIME_ZONE)


def _clean(text: str) -> str:
    # Impede que o texto do cliente feche ou abra as tags do contexto.
    return text.replace("<", chr(0x2039)).replace(">", chr(0x203A)).strip()


def _when(value: datetime | None) -> str:
    return value.astimezone(TZ).strftime("%d/%m/%Y %H:%M") if value else ""


def _day(value: datetime | None) -> str:
    return value.astimezone(TZ).strftime("%d/%m/%Y") if value else "sem registro"


def build_triage_context(conversation: Conversation) -> str:
    tenant = Tenant.objects.get(pk=conversation.tenant_id)
    parts = [f"<escritorio>{_clean(tenant.name)}</escritorio>"]

    client = conversation.client
    if client is None:
        parts.append(
            "<cliente>Não identificado. Pode ser um cliente novo. "
            f"Nome no perfil do WhatsApp: {_clean(conversation.contact_name) or 'não informado'}."
            "</cliente>"
        )
        parts.append("<processos>Nenhum processo associado.</processos>")
    else:
        parts.append(
            f"<cliente>Nome: {_clean(client.name)}. Situação: {client.get_status_display()}."
            "</cliente>"
        )
        cases = LegalCase.objects.filter(
            case_clients__client=client, status=LegalCase.Status.ACTIVE
        ).order_by("-created_at")[:10]
        lines = [
            "- "
            + " | ".join(
                [
                    case.cnj_formatted,
                    case.tribunal_label or "tribunal não identificado",
                    f"classe: {_clean(case.classe) or 'não informada'}",
                    f"assunto: {_clean(case.assunto) or 'não informado'}",
                    f"órgão: {_clean(case.orgao_julgador) or 'não informado'}",
                    f"última movimentação registrada: {_day(case.last_movement_at)}",
                ]
            )
            for case in cases
        ]
        parts.append(
            "<processos>\n"
            + ("\n".join(lines) or "Nenhum processo ativo cadastrado.")
            + "\n</processos>"
        )

    recent = list(
        Message.objects.filter(conversation=conversation)
        .exclude(status=Message.Status.FAILED)
        .order_by("-created_at")[: settings.TRIAGE_HISTORY_MESSAGES]
    )
    transcript = []
    for m in reversed(recent):
        who = "Cliente" if m.direction == Message.Direction.INBOUND else "Escritório"
        body = _clean(m.body) if m.body else f"[{m.get_type_display()} sem texto]"
        transcript.append(f"[{_when(m.wa_timestamp or m.created_at)}] {who}: {body}")
    parts.append("<conversa>\n" + "\n".join(transcript) + "\n</conversa>")

    parts.append(
        "Faça a triagem das últimas mensagens do Cliente e escreva o rascunho de resposta."
    )
    return "\n\n".join(parts)

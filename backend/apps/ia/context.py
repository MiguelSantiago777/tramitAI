"""Monta o contexto da triagem a partir do banco (tenant ativo).

Só entra o que é necessário: dados do cliente vinculado e dos processos dele, e as últimas
mensagens. Cliente só sugerido (por CPF) NÃO entra: CPF digitado não prova identidade.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

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


def _agenda_parts(conversation: Conversation) -> list[str]:
    """Expediente (a Vera avisa fora dele) e horários livres que ela pode oferecer.

    Guarda os horários oferecidos na conversa: quando o contato escolher "H2", a reserva usa
    exatamente o horário que ele viu.
    """
    from apps.agenda import scheduling
    from apps.tenants.models import TenantSettings

    cfg = TenantSettings.objects.first()
    if cfg is None:
        return []
    now = timezone.now()
    status = "aberto agora" if scheduling.is_open(cfg, now) else "fora do horário agora"
    local_now = now.astimezone(TZ)
    parts = [
        f"<expediente>Horário de atendimento: {scheduling.hours_text(cfg)}. "
        f"Agora é {scheduling.WEEKDAYS[local_now.weekday()]}, {local_now:%d/%m %H:%M}: "
        f"{status}.</expediente>"
    ]
    offered: list[dict[str, str]] = []
    if cfg.scheduling_enabled:
        # Mantém a lista que o contato já viu (para "a primeira opção" ser o mesmo horário);
        # só recalcula quando não há oferta válida (passou do prazo ou foi tudo ocupado).
        valid = [
            o
            for o in conversation.offered_slots
            if datetime.fromisoformat(o["start"]) > now + scheduling.MIN_LEAD
        ]
        if valid and any(
            scheduling.is_free(cfg, datetime.fromisoformat(o["start"])) for o in valid
        ):
            offered = valid
        else:
            slots = scheduling.free_slots(cfg, now=now)
            offered = [{"id": f"H{i}", "start": s.isoformat()} for i, s in enumerate(slots, 1)]
        lines = []
        for o in offered:
            start = datetime.fromisoformat(o["start"])
            taken = "" if scheduling.is_free(cfg, start) else " (não está mais livre)"
            lines.append(f"{o['id']}: {scheduling.slot_label(start)}{taken}")
        parts.append(
            "<horarios_livres>\n"
            + ("\n".join(lines) or "Nenhum horário livre nos próximos dias.")
            + f"\nDuração da consulta: {cfg.consult_minutes} minutos.\n</horarios_livres>"
        )
    Conversation.objects.filter(pk=conversation.pk).update(offered_slots=offered)
    return parts


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

    parts.extend(_agenda_parts(conversation))

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

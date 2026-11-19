"""Confere, pelas mensagens do cliente, se ele escolheu mesmo o horário e o formato da consulta.

A IA às vezes "chuta" (ex.: o cliente responde só "online" e ela reserva o primeiro horário).
Antes de pré-reservar, procuramos no texto do cliente sinais do horário (dia da semana, data,
hora, "a primeira opção"...) e do formato (online/presencial). Se não bater com o que a IA
escolheu, não reserva: a resposta vira uma pergunta só sobre o que falta.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.utils import timezone

from apps.agenda import scheduling
from apps.whatsapp.models import Conversation, Message

TZ = scheduling.TZ
WEEKDAY_WORDS = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
ORDINALS = {
    1: [r"\bprimeir[oa]\b", r"\b1(?:o|a|º|ª)\b"],
    2: [r"\bsegundo\b", r"\bsegunda (?:opcao|op|horario|alternativa)\b", r"\b2(?:o|a|º|ª)\b"],
    3: [r"\bterceir[oa]\b", r"\b3(?:o|a|º|ª)\b"],
}
MODE_WORDS = {
    "online": [
        r"\bon ?line\b",
        r"\bvideo",
        r"\bchamada\b",
        r"\bremot",
        r"\bvirtual\b",
        r"\bmeet\b",
        r"\bzoom\b",
        r"\btelefone\b",
        r"\bligacao\b",
        r"\bpelo (?:whats|zap|celular)",
    ],
    "presencial": [
        r"\bpresencia",
        r"\bpessoalmente\b",
        r"\bno escritorio\b",
        r"\bir ai\b",
        r"\bvou ai\b",
        r"\bvou ate\b",
        r"\bir ate\b",
        r"\bao vivo\b",
    ],
}
AFFIRMATIVE = re.compile(
    r"^(?:sim|s|pode|pode sim|pode ser|ok|okay|isso|isso mesmo|confirmo|confirmado|fechado|"
    r"beleza|blz|perfeito|certo|combinado|claro|otimo|show|uhum|aham)\b"
)
MODE_LABEL = {"online": "online", "presencial": "presencial, no escritório"}


def normalize(text: str) -> str:
    plain = unicodedata.normalize("NFKD", (text or "").lower())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    plain = re.sub(r"[^a-z0-9:/ºª\n ]", " ", plain)
    return re.sub(r"[ \t]+", " ", plain).strip()


@dataclass(frozen=True)
class Check:
    slot_id: str | None  # horário que o cliente apontou (só se for um único)
    mode: str | None  # "online" / "presencial", se o cliente disse
    ok: bool  # bate com o que a IA quer reservar
    reply: str  # pergunta para o cliente quando não bate
    needs_lawyer: bool = False  # nenhum horário oferecido segue livre


def _slot_score(text: str, index: int, start: datetime, now: datetime) -> int:
    """Quantos tipos de pista no texto apontam para este horário."""
    local = start.astimezone(TZ)
    h, m = local.hour, local.minute
    hour = [
        rf"\b0?{h}(?::{m:02d}|h{m:02d})\b",
        rf"\b0?{h} ?(?:h|hs|hrs|hr|horas?)\b" if m == 0 else rf"\b0?{h} ?e ?{m}\b",
        rf"\bas 0?{h}\b" if m == 0 else rf"\bas 0?{h}:{m:02d}\b",
    ]
    if h > 12:
        hour.append(rf"\b{h - 12} ?(?:h|horas?)? da tarde\b")
    elif h < 12:
        hour.append(rf"\b{h} ?(?:h|horas?)? da manha\b")
    weekday = WEEKDAY_WORDS[local.weekday()]
    day = [rf"\b{weekday}\b(?! ?(?:opcao|op|horario|alternativa))"]
    date = [rf"\b0?{local.day}/0?{local.month}\b", rf"\bdia 0?{local.day}\b"]
    today = now.astimezone(TZ).date()
    relative = []
    if local.date() == today:
        relative.append(r"\bhoje\b")
    elif local.date() == today + timedelta(days=1):
        relative.append(r"(?<!depois de )\bamanha\b")
    elif local.date() == today + timedelta(days=2):
        relative.append(r"\bdepois de amanha\b")
    order = [*ORDINALS.get(index, []), rf"\b(?:opcao|horario|numero|h) ?{index}\b"]
    groups = [hour, day, date, relative, order]
    return sum(1 for group in groups if any(re.search(p, text) for p in group))


def _pick_slot(text: str, offered: list[dict[str, str]], now: datetime) -> str | None:
    scores = [
        (_slot_score(text, i, datetime.fromisoformat(o["start"]), now), o["id"])
        for i, o in enumerate(offered, 1)
    ]
    best = max((s for s, _ in scores), default=0)
    winners = [slot_id for s, slot_id in scores if s == best]
    return winners[0] if best > 0 and len(winners) == 1 else None


def _modes_in(text: str) -> set[str]:
    return {mode for mode, words in MODE_WORDS.items() if any(re.search(w, text) for w in words)}


def _labels(offered: list[dict[str, str]]) -> str:
    labels = [scheduling.slot_label(datetime.fromisoformat(o["start"])) for o in offered]
    if len(labels) <= 1:
        return "".join(labels)
    return ", ".join(labels[:-1]) + " ou " + labels[-1]


def check(conversation: Conversation, slot_id: str, mode: str) -> Check:
    offered = list(conversation.offered_slots or [])
    now = timezone.now()
    messages = list(
        Message.objects.filter(
            conversation=conversation, created_at__gte=now - timedelta(days=2)
        ).order_by("created_at")
    )
    # Mensagens do cliente desde a última oferta de horários (mensagem nossa com a hora de
    # algum horário oferecido). Sem oferta reconhecível: desde a nossa última mensagem.
    hours = {f"{datetime.fromisoformat(o['start']).astimezone(TZ):%H:%M}" for o in offered}
    anchor = -1
    for i, msg in enumerate(messages):
        if msg.direction == Message.Direction.OUTBOUND and any(h in msg.body for h in hours):
            anchor = i
    if anchor < 0:
        anchor = max(
            (i for i, m in enumerate(messages) if m.direction == Message.Direction.OUTBOUND),
            default=-1,
        )
    inbound = [
        normalize(m.body)
        for m in messages[anchor + 1 :]
        if m.direction == Message.Direction.INBOUND and m.body
    ]
    last_out = next(
        (
            normalize(m.body)
            for m in reversed(messages)
            if m.direction == Message.Direction.OUTBOUND
        ),
        "",
    )
    affirmative = bool(inbound) and bool(AFFIRMATIVE.match(inbound[-1]))

    # Horário: primeiro só a última mensagem; se não decidir, todas desde a oferta.
    # "Sim" depois de "Posso reservar quinta às 10h?" vale a nossa pergunta.
    candidates = [inbound[-1]] if inbound else []
    candidates.append("\n".join(inbound))
    if affirmative and last_out:
        candidates.append(last_out)
    chosen = None
    for text in candidates:
        chosen = _pick_slot(text, offered, now)
        if chosen:
            break

    # Formato: a mensagem mais recente do cliente (dos últimos 2 dias) que fala disso.
    said_mode: str | None = None
    recent_in = [
        normalize(m.body)
        for m in reversed(messages)
        if m.direction == Message.Direction.INBOUND and m.body
    ]
    if affirmative and last_out:
        recent_in.insert(0, last_out)
    for text in recent_in:
        modes = _modes_in(text)
        if len(modes) == 1:
            said_mode = modes.pop()
            break
        if len(modes) > 1:
            said_mode = mode if mode in modes else None
            break

    if chosen == slot_id and said_mode == mode:
        return Check(chosen, said_mode, True, "")

    from apps.tenants.models import TenantSettings

    cfg = TenantSettings.objects.first()
    free = [
        o
        for o in offered
        if cfg is not None and scheduling.is_free(cfg, datetime.fromisoformat(o["start"]))
    ]
    by_id = {o["id"]: o for o in offered}
    if not free:
        reply = (
            "Os horários que eu ofereci já foram preenchidos. O(a) advogado(a) vai combinar "
            "outro horário com você por aqui."
        )
        return Check(chosen, said_mode, False, reply, needs_lawyer=True)
    if chosen and said_mode:
        label = scheduling.slot_label(datetime.fromisoformat(by_id[chosen]["start"]))
        reply = f"Só para confirmar: posso pré-reservar {label}, {MODE_LABEL[said_mode]}?"
    elif chosen:
        label = scheduling.slot_label(datetime.fromisoformat(by_id[chosen]["start"]))
        reply = f"Ótimo, {label}. Você prefere presencial, no escritório, ou online?"
    elif said_mode:
        reply = (
            f"Combinado, {MODE_LABEL[said_mode]}! Qual destes horários fica melhor para "
            f"você: {_labels(free)}?"
        )
    else:
        reply = (
            f"Qual destes horários fica melhor para você: {_labels(free)}? "
            "E prefere presencial, no escritório, ou online?"
        )
    return Check(chosen, said_mode, False, reply)

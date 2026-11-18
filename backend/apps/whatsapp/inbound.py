"""Tradução do payload do webhook da Meta para estruturas internas. Funções puras, sem banco."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .models import Message

_KNOWN_TYPES = {t.value for t in Message.Type}


@dataclass(frozen=True)
class InboundMessage:
    phone_number_id: str
    wa_id: str
    contact_name: str
    wa_message_id: str
    type: str
    body: str
    media_id: str
    timestamp: datetime
    media_filename: str = ""
    # A ponte avisa quando não conseguiu baixar (ex.: grande demais): não adianta buscar.
    media_error: str = ""


@dataclass(frozen=True)
class StatusUpdate:
    phone_number_id: str
    wa_message_id: str
    status: str  # sent | delivered | read | failed
    timestamp: datetime
    error_code: str
    error_detail: str


def _ts(value: Any) -> datetime:
    try:
        return datetime.fromtimestamp(int(value), tz=UTC)
    except TypeError, ValueError:
        return datetime.now(tz=UTC)


def _content(message: dict[str, Any]) -> tuple[str, str, str]:
    """(tipo, texto, media_id) de uma mensagem recebida."""
    kind = str(message.get("type", "other"))
    if kind == "text":
        return Message.Type.TEXT, str(message.get("text", {}).get("body", "")), ""
    if kind == "button":
        return Message.Type.TEXT, str(message.get("button", {}).get("text", "")), ""
    if kind == "interactive":
        interactive = message.get("interactive", {})
        reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
        return Message.Type.TEXT, str(reply.get("title", "")), ""
    if kind in ("image", "video", "document", "audio"):
        media = message.get(kind, {})
        return kind, str(media.get("caption", "")), str(media.get("id", ""))
    if kind == "sticker":
        return kind, "", ""  # figurinha não vai para a pasta do cliente
    if kind in _KNOWN_TYPES:
        return kind, "", ""
    return Message.Type.OTHER, "", ""


def parse_payload(payload: dict[str, Any]) -> tuple[list[InboundMessage], list[StatusUpdate]]:
    messages: list[InboundMessage] = []
    statuses: list[StatusUpdate] = []

    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            if change.get("field") != "messages":
                continue
            value = change.get("value", {}) or {}
            phone_number_id = str(value.get("metadata", {}).get("phone_number_id", ""))
            if not phone_number_id:
                continue
            names = {
                str(c.get("wa_id", "")): str(c.get("profile", {}).get("name", ""))
                for c in value.get("contacts", []) or []
            }
            for raw in value.get("messages", []) or []:
                wa_id = str(raw.get("from", ""))
                if not wa_id or not raw.get("id"):
                    continue
                kind, body, media_id = _content(raw)
                filename = str((raw.get("document") or {}).get("filename", ""))[:200]
                messages.append(
                    InboundMessage(
                        phone_number_id=phone_number_id,
                        wa_id=wa_id,
                        contact_name=names.get(wa_id, ""),
                        wa_message_id=str(raw["id"]),
                        type=kind,
                        body=body,
                        media_id=media_id,
                        timestamp=_ts(raw.get("timestamp")),
                        media_filename=filename,
                    )
                )
            for raw in value.get("statuses", []) or []:
                if not raw.get("id"):
                    continue
                error = (raw.get("errors") or [{}])[0]
                statuses.append(
                    StatusUpdate(
                        phone_number_id=phone_number_id,
                        wa_message_id=str(raw["id"]),
                        status=str(raw.get("status", "")),
                        timestamp=_ts(raw.get("timestamp")),
                        error_code=str(error.get("code", ""))[:32],
                        error_detail=str(error.get("title") or error.get("message") or "")[:255],
                    )
                )
    return messages, statuses


# ---------------------------------------------------------------- ponte Baileys

_BRIDGE_TYPES = {"text", "image", "audio", "video", "document", "sticker", "location", "other"}
_BRIDGE_STATUSES = {"sent", "delivered", "read", "failed"}


@dataclass(frozen=True)
class ConnectionUpdate:
    phone_number_id: str  # id da sessão na ponte
    status: str  # open | connecting | logged_out
    phone: str


def parse_bridge_payload(
    payload: dict[str, Any],
) -> tuple[list[InboundMessage], list[StatusUpdate], list[ConnectionUpdate]]:
    """Evento da ponte → mesmas estruturas do webhook da Meta (+ estado da conexão)."""
    from .gateway.bridge import message_id

    session = str(payload.get("session_id") or "")
    messages: list[InboundMessage] = []
    statuses: list[StatusUpdate] = []
    connections: list[ConnectionUpdate] = []
    if not session:
        return messages, statuses, connections

    event = payload.get("event")
    if event == "messages":
        for raw in payload.get("messages") or []:
            if not isinstance(raw, dict) or not raw.get("id") or not raw.get("from"):
                continue
            kind = str(raw.get("type") or "other")
            media = raw.get("media") if isinstance(raw.get("media"), dict) else None
            messages.append(
                InboundMessage(
                    phone_number_id=session,
                    wa_id=str(raw["from"])[:32],
                    contact_name=str(raw.get("name") or "")[:200],
                    wa_message_id=message_id(str(raw["id"])),
                    type=kind if kind in _BRIDGE_TYPES else "other",
                    body=str(raw.get("text") or ""),
                    # Na ponte, a mídia é buscada pelo id da mensagem (sem o prefixo).
                    media_id=str(raw["id"])[:128] if media else "",
                    timestamp=_ts(raw.get("timestamp")),
                    media_filename=str((media or {}).get("filename") or "")[:200],
                    media_error=str((media or {}).get("error") or "")[:32],
                )
            )
    elif event == "statuses":
        for raw in payload.get("statuses") or []:
            if not isinstance(raw, dict) or raw.get("status") not in _BRIDGE_STATUSES:
                continue
            statuses.append(
                StatusUpdate(
                    phone_number_id=session,
                    wa_message_id=message_id(str(raw.get("id"))),
                    status=str(raw["status"]),
                    timestamp=_ts(raw.get("timestamp")),
                    error_code="",
                    error_detail="",
                )
            )
    elif event == "connection":
        connections.append(
            ConnectionUpdate(
                phone_number_id=session,
                status=str(payload.get("status") or ""),
                phone=str(payload.get("phone") or ""),
            )
        )
    return messages, statuses, connections

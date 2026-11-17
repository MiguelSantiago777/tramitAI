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
    if kind in ("image", "video", "document", "audio", "sticker"):
        media = message.get(kind, {})
        return kind, str(media.get("caption", "")), str(media.get("id", ""))
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

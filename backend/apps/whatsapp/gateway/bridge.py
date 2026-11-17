"""Ponte Baileys (serviço `bridge`): envio de texto e controle da sessão do escritório.

A ponte fica na rede interna; autenticação por Bearer com WHATSAPP_BRIDGE_SECRET. As
chamadas são HTTP: nunca dentro de transação aberta.
"""

import logging
from dataclasses import dataclass
from typing import Any

import httpx
from django.conf import settings

from .base import Credentials, GatewayError, SendResult

logger = logging.getLogger(__name__)

# Prefixo dos ids do Baileys no nosso banco (wa_message_id é único global).
MESSAGE_ID_PREFIX = "bl:"


def message_id(raw: str) -> str:
    return f"{MESSAGE_ID_PREFIX}{raw}"


class BridgeUnavailable(Exception):
    """A ponte não respondeu (container parado, rede)."""


@dataclass(frozen=True)
class SessionInfo:
    status: str  # not_started | connecting | qr | open | closed | logged_out
    qr: str | None  # data URL da imagem do QR Code
    phone: str | None


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=settings.WHATSAPP_BRIDGE_URL.rstrip("/"),
        timeout=settings.WHATSAPP_BRIDGE_TIMEOUT,
        headers={"Authorization": f"Bearer {settings.WHATSAPP_BRIDGE_SECRET}"},
    )


class BridgeGateway:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or _client()

    def send_text(self, credentials: Credentials, *, to: str, body: str) -> SendResult:
        try:
            response = self._client.post(
                f"/sessions/{credentials.phone_number_id}/messages",
                json={"to": to, "text": body},
            )
        except httpx.ConnectError as exc:
            raise GatewayError("bridge_down", "ponte indisponível", retryable=True) from exc
        except httpx.HTTPError as exc:
            # A ponte pode ter enviado e demorado a responder: não reenviar sozinho.
            raise GatewayError("uncertain", type(exc).__name__, retryable=False) from exc

        if response.is_success:
            try:
                return SendResult(wa_message_id=message_id(str(response.json()["id"])))
            except (ValueError, KeyError, TypeError) as exc:
                raise GatewayError("bad_response", "resposta sem id", retryable=False) from exc

        code = _error_code(response)
        logger.warning("bridge send failed status=%s code=%s", response.status_code, code)
        if response.status_code == 409:
            # Sessão caiu/reconectando: a mensagem não saiu. Tenta de novo com backoff.
            raise GatewayError(
                "not_connected", "WhatsApp do escritório desconectado.", retryable=True
            )
        if response.status_code == 422:
            raise GatewayError("not_on_whatsapp", "Este número não tem WhatsApp.", retryable=False)
        if response.status_code == 503:
            raise GatewayError("lookup_failed", "Falha ao consultar o número.", retryable=True)
        raise GatewayError(code, "Falha no envio pela ponte.", retryable=False)

    def send_template(
        self,
        credentials: Credentials,
        *,
        to: str,
        name: str,
        language: str,
        params: list[str],
    ) -> SendResult:
        # WhatsApp Web não tem templates nem janela de 24h: nunca deveria chegar aqui.
        raise GatewayError("unsupported", "Modelo da Meta não existe no Baileys.", retryable=False)


def _error_code(response: httpx.Response) -> str:
    try:
        return str(response.json().get("error") or response.status_code)
    except ValueError:
        return str(response.status_code)


# ---------------------------------------------------------------- sessão (pareamento)


def _session_call(method: str, path: str, client: httpx.Client | None = None) -> Any:
    http = client or _client()
    try:
        response = http.request(method, path)
    except httpx.HTTPError as exc:
        raise BridgeUnavailable(type(exc).__name__) from exc
    if response.status_code >= 500 or response.status_code == 401:
        raise BridgeUnavailable(f"http_{response.status_code}")
    return response.json() if response.content else None


def _info(data: Any) -> SessionInfo:
    data = data or {}
    return SessionInfo(
        status=str(data.get("status") or "not_started"),
        qr=data.get("qr") or None,
        phone=data.get("phone") or None,
    )


def session_info(session_id: str, client: httpx.Client | None = None) -> SessionInfo:
    return _info(_session_call("GET", f"/sessions/{session_id}", client))


def start_session(session_id: str, client: httpx.Client | None = None) -> SessionInfo:
    return _info(_session_call("POST", f"/sessions/{session_id}/start", client))


def logout_session(session_id: str, client: httpx.Client | None = None) -> None:
    _session_call("DELETE", f"/sessions/{session_id}", client)

"""WhatsApp Cloud API (Meta), direto, sem BSP."""

import logging
from typing import Any

import httpx
from django.conf import settings

from .base import Credentials, GatewayError, MediaFile, SendResult

logger = logging.getLogger(__name__)

# Erros da Meta em que a mensagem comprovadamente não foi aceita e vale tentar de novo.
_RETRYABLE_HTTP = {429, 503}


class CloudApiGateway:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=settings.WHATSAPP_HTTP_TIMEOUT)

    def _url(self, phone_number_id: str) -> str:
        base = settings.WHATSAPP_GRAPH_URL.rstrip("/")
        return f"{base}/{settings.WHATSAPP_GRAPH_VERSION}/{phone_number_id}/messages"

    def send_text(self, credentials: Credentials, *, to: str, body: str) -> SendResult:
        return self._send(
            credentials,
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "text",
                "text": {"preview_url": False, "body": body},
            },
        )

    def send_template(
        self,
        credentials: Credentials,
        *,
        to: str,
        name: str,
        language: str,
        params: list[str],
    ) -> SendResult:
        template: dict[str, Any] = {"name": name, "language": {"code": language}}
        if params:
            template["components"] = [
                {"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}
            ]
        return self._send(
            credentials,
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "template",
                "template": template,
            },
        )

    def send_media(
        self,
        credentials: Credentials,
        *,
        to: str,
        kind: str,
        media: MediaFile,
        caption: str = "",
    ) -> SendResult:
        """Dois passos: sobe o arquivo para a Meta (devolve um id) e manda a mensagem com ele."""
        media_id = self._upload(credentials, media)
        body: dict[str, Any] = {"id": media_id}
        if caption and kind != "audio":
            body["caption"] = caption
        if kind == "document" and media.filename:
            body["filename"] = media.filename
        return self._send(
            credentials,
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": kind,
                kind: body,
            },
        )

    def _upload(self, credentials: Credentials, media: MediaFile) -> str:
        base = settings.WHATSAPP_GRAPH_URL.rstrip("/")
        url = f"{base}/{settings.WHATSAPP_GRAPH_VERSION}/{credentials.phone_number_id}/media"
        try:
            response = self._client.post(
                url,
                data={"messaging_product": "whatsapp", "type": media.content_type},
                files={"file": (media.filename or "arquivo", media.content, media.content_type)},
                headers={"Authorization": f"Bearer {credentials.access_token}"},
                timeout=max(settings.WHATSAPP_HTTP_TIMEOUT, 60.0),
            )
        except httpx.HTTPError as exc:
            # Subir o arquivo não manda nada para o cliente: dá para tentar de novo.
            raise GatewayError("upload_failed", type(exc).__name__, retryable=True) from exc
        if not response.is_success:
            raise _error_from(response)
        try:
            return str(response.json()["id"])
        except (ValueError, KeyError, TypeError) as exc:
            raise GatewayError("bad_response", "upload sem id", retryable=False) from exc

    def _send(self, credentials: Credentials, payload: dict[str, Any]) -> SendResult:
        try:
            response = self._client.post(
                self._url(credentials.phone_number_id),
                json=payload,
                headers={"Authorization": f"Bearer {credentials.access_token}"},
            )
        except httpx.ConnectError as exc:
            # Não conectou: o request não saiu.
            raise GatewayError("connect_error", str(exc), retryable=True) from exc
        except httpx.HTTPError as exc:
            # Timeout de leitura etc.: pode ter sido aceito pela Meta. Não reenviar sozinho.
            raise GatewayError("uncertain", type(exc).__name__, retryable=False) from exc

        if response.is_success:
            data = response.json()
            try:
                return SendResult(wa_message_id=str(data["messages"][0]["id"]))
            except (KeyError, IndexError, TypeError) as exc:
                raise GatewayError("bad_response", "resposta sem id", retryable=False) from exc

        error = _error_from(response)
        logger.warning("whatsapp send failed status=%s code=%s", response.status_code, error.code)
        raise error

    def download_media(self, credentials: Credentials, *, media_id: str) -> MediaFile:
        """Dois passos da Meta: metadados (URL temporária) e depois o arquivo, ambos com token."""
        base = settings.WHATSAPP_GRAPH_URL.rstrip("/")
        headers = {"Authorization": f"Bearer {credentials.access_token}"}
        try:
            meta = self._client.get(
                f"{base}/{settings.WHATSAPP_GRAPH_VERSION}/{media_id}", headers=headers
            )
            if not meta.is_success:
                raise _error_from(meta)
            info = meta.json()
            size = int(info.get("file_size") or 0)
            if size > settings.DOCUMENT_MAX_BYTES:
                raise GatewayError("media_too_large", "Arquivo grande demais.", retryable=False)
            response = self._client.get(str(info["url"]), headers=headers)
        except httpx.HTTPError as exc:
            # Download é idempotente: pode tentar de novo sem risco.
            raise GatewayError("connect_error", type(exc).__name__, retryable=True) from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise GatewayError("bad_response", "mídia sem URL", retryable=False) from exc
        if not response.is_success:
            raise _error_from(response)
        if len(response.content) > settings.DOCUMENT_MAX_BYTES:
            raise GatewayError("media_too_large", "Arquivo grande demais.", retryable=False)
        return MediaFile(
            content=response.content,
            content_type=str(info.get("mime_type") or response.headers.get("content-type", "")),
        )

    def release_media(self, credentials: Credentials, *, media_id: str) -> None:
        return None  # a Meta apaga sozinha depois de 30 dias


def _error_from(response: httpx.Response) -> GatewayError:
    try:
        err = response.json().get("error", {})
    except ValueError:
        err = {}
    code = str(err.get("code") or response.status_code)
    detail = str(err.get("error_user_msg") or err.get("message") or response.reason_phrase)
    return GatewayError(code, detail, retryable=response.status_code in _RETRYABLE_HTTP)

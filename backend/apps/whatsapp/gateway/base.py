"""Interface de envio para o WhatsApp. O resto do sistema só conhece isto, nunca a Meta."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Credentials:
    phone_number_id: str
    access_token: str


@dataclass(frozen=True)
class SendResult:
    wa_message_id: str


@dataclass(frozen=True)
class MediaFile:
    content: bytes
    content_type: str
    filename: str = ""


class GatewayError(Exception):
    """Falha de envio.

    retryable=True: temos certeza de que a mensagem NÃO saiu (ex.: conexão recusada, 429),
    então dá para tentar de novo. Em qualquer dúvida (timeout depois de enviar o request),
    retryable=False: melhor um humano reenviar do que o cliente receber duas vezes.
    """

    def __init__(self, code: str, detail: str, *, retryable: bool) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail[:255]
        self.retryable = retryable


class WhatsAppGateway(Protocol):
    def send_text(self, credentials: Credentials, *, to: str, body: str) -> SendResult: ...

    def send_template(
        self,
        credentials: Credentials,
        *,
        to: str,
        name: str,
        language: str,
        params: list[str],
    ) -> SendResult: ...

    def send_media(
        self,
        credentials: Credentials,
        *,
        to: str,
        kind: str,
        media: MediaFile,
        caption: str = "",
    ) -> SendResult:
        """Envia um arquivo. `kind`: image | video | audio | document (áudio não tem legenda)."""
        ...

    def download_media(self, credentials: Credentials, *, media_id: str) -> MediaFile: ...

    def release_media(self, credentials: Credentials, *, media_id: str) -> None:
        """Avisa o provedor que a mídia já foi guardada (a ponte apaga a cópia temporária)."""
        ...

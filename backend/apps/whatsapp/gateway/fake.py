"""Gateway falso para dev e testes: não fala com a Meta, só registra o que seria enviado."""

import uuid
from dataclasses import dataclass, field

from .base import Credentials, GatewayError, MediaFile, SendResult


@dataclass
class SentMessage:
    phone_number_id: str
    to: str
    body: str
    template: str = ""
    params: list[str] = field(default_factory=list)
    kind: str = ""
    filename: str = ""
    content_type: str = ""


@dataclass
class FakeGateway:
    sent: list[SentMessage] = field(default_factory=list)
    # Para testes: próxima chamada falha com este erro.
    fail_next: GatewayError | None = None
    # Mídias "disponíveis" no provedor, por media_id. Sem cadastro: devolve um PDF mínimo.
    media: dict[str, MediaFile] = field(default_factory=dict)
    released: list[str] = field(default_factory=list)

    def send_text(self, credentials: Credentials, *, to: str, body: str) -> SendResult:
        if self.fail_next is not None:
            error, self.fail_next = self.fail_next, None
            raise error
        self.sent.append(SentMessage(credentials.phone_number_id, to, body))
        return SendResult(wa_message_id=f"wamid.fake.{uuid.uuid4().hex}")

    def send_template(
        self,
        credentials: Credentials,
        *,
        to: str,
        name: str,
        language: str,
        params: list[str],
    ) -> SendResult:
        if self.fail_next is not None:
            error, self.fail_next = self.fail_next, None
            raise error
        self.sent.append(
            SentMessage(credentials.phone_number_id, to, "", template=name, params=list(params))
        )
        return SendResult(wa_message_id=f"wamid.fake.{uuid.uuid4().hex}")

    def send_media(
        self,
        credentials: Credentials,
        *,
        to: str,
        kind: str,
        media: MediaFile,
        caption: str = "",
    ) -> SendResult:
        if self.fail_next is not None:
            error, self.fail_next = self.fail_next, None
            raise error
        self.sent.append(
            SentMessage(
                credentials.phone_number_id,
                to,
                caption,
                kind=kind,
                filename=media.filename,
                content_type=media.content_type,
            )
        )
        return SendResult(wa_message_id=f"wamid.fake.{uuid.uuid4().hex}")

    def download_media(self, credentials: Credentials, *, media_id: str) -> MediaFile:
        if self.fail_next is not None:
            error, self.fail_next = self.fail_next, None
            raise error
        return self.media.get(
            media_id, MediaFile(b"%PDF-1.4 fake", "application/pdf", "documento.pdf")
        )

    def release_media(self, credentials: Credentials, *, media_id: str) -> None:
        self.released.append(media_id)

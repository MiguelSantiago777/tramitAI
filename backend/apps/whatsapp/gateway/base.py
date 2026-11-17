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

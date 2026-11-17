"""Gateway falso para dev e testes: não fala com a Meta, só registra o que seria enviado."""

import uuid
from dataclasses import dataclass, field

from .base import Credentials, GatewayError, SendResult


@dataclass
class SentMessage:
    phone_number_id: str
    to: str
    body: str


@dataclass
class FakeGateway:
    sent: list[SentMessage] = field(default_factory=list)
    # Para testes: próxima chamada falha com este erro.
    fail_next: GatewayError | None = None

    def send_text(self, credentials: Credentials, *, to: str, body: str) -> SendResult:
        if self.fail_next is not None:
            error, self.fail_next = self.fail_next, None
            raise error
        self.sent.append(SentMessage(credentials.phone_number_id, to, body))
        return SendResult(wa_message_id=f"wamid.fake.{uuid.uuid4().hex}")

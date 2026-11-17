import json
from collections.abc import Callable
from typing import Any

import pytest
from django.conf import settings

from apps.tenants.services import CreatedTenant
from apps.whatsapp.gateway import FakeGateway, get_gateway
from apps.whatsapp.management.commands.simulate_inbound import build_payload
from apps.whatsapp.models import WhatsAppAccount
from apps.whatsapp.services import register_account
from apps.whatsapp.signature import sign

NUMBER_A = "111000111"
NUMBER_B = "222000222"
TOKEN_A = "EAAG-token-secreto-do-escritorio-A"
WEBHOOK = "/api/webhooks/whatsapp/"


@pytest.fixture
def account_a(tenant_a: CreatedTenant) -> WhatsAppAccount:
    return register_account(
        tenant=tenant_a.tenant,
        phone_number_id=NUMBER_A,
        waba_id="waba-a",
        display_phone="+55 21 3000-0001",
        access_token=TOKEN_A,
    )


@pytest.fixture
def account_b(tenant_b: CreatedTenant) -> WhatsAppAccount:
    return register_account(
        tenant=tenant_b.tenant,
        phone_number_id=NUMBER_B,
        waba_id="waba-b",
        display_phone="+55 21 3000-0002",
        access_token="token-b",
    )


@pytest.fixture
def fake_gateway() -> FakeGateway:
    gateway = get_gateway()
    assert isinstance(gateway, FakeGateway)
    gateway.sent.clear()
    gateway.fail_next = None
    return gateway


@pytest.fixture
def post_webhook(client: Any, django_capture_on_commit_callbacks: Any) -> Callable[..., Any]:
    """Posta um payload assinado no webhook e executa os on_commit (a task roda eager)."""

    def _post(payload: dict[str, Any], *, signature: str | None = "valid") -> Any:
        body = json.dumps(payload).encode()
        headers = {}
        if signature == "valid":
            headers["X-Hub-Signature-256"] = sign(body, settings.WHATSAPP_APP_SECRET)
        elif signature is not None:
            headers["X-Hub-Signature-256"] = signature
        with django_capture_on_commit_callbacks(execute=True):
            return client.post(WEBHOOK, data=body, content_type="application/json", headers=headers)

    return _post


@pytest.fixture
def inbound(post_webhook: Callable[..., Any]) -> Callable[..., Any]:
    """Simula uma mensagem de texto recebida num número."""

    def _inbound(
        text: str = "Oi, queria saber do meu processo",
        *,
        number: str = NUMBER_A,
        wa_id: str = "5521998765432",
        name: str = "Maria",
    ) -> Any:
        payload = build_payload(phone_number_id=number, wa_id=wa_id, name=name, text=text)
        return post_webhook(payload)

    return _inbound


def status_payload(number: str, wamid: str, status: str, ts: int = 1_700_000_000) -> dict[str, Any]:
    value: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "metadata": {"phone_number_id": number},
        "statuses": [
            {"id": wamid, "status": status, "timestamp": str(ts), "recipient_id": "5521998765432"}
        ],
    }
    if status == "failed":
        value["statuses"][0]["errors"] = [{"code": 131047, "title": "Re-engagement message"}]
    return {"entry": [{"changes": [{"field": "messages", "value": value}]}]}

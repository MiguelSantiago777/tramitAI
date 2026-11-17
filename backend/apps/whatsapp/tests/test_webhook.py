import json
import logging

import pytest
from django.conf import settings

from apps.clientes.models import Client
from apps.core.tenancy import tenant_context
from apps.whatsapp.management.commands.simulate_inbound import build_payload
from apps.whatsapp.models import Conversation, InboundWebhookEvent, Message
from apps.whatsapp.signature import sign
from apps.whatsapp.tasks import process_inbound_event

from .fixtures import NUMBER_A, NUMBER_B, WEBHOOK

pytestmark = pytest.mark.django_db


# ------------------------------------------------------------------ verificação e assinatura


def test_verify_challenge(client):
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": settings.WHATSAPP_VERIFY_TOKEN,
        "hub.challenge": "12345",
    }
    response = client.get(WEBHOOK, params)
    assert response.status_code == 200
    assert response.content == b"12345"


def test_verify_with_wrong_token(client):
    params = {"hub.mode": "subscribe", "hub.verify_token": "errado", "hub.challenge": "1"}
    assert client.get(WEBHOOK, params).status_code == 403


@pytest.mark.parametrize("signature", [None, "sha256=deadbeef", "md5=abc"])
def test_rejects_missing_or_invalid_signature(account_a, post_webhook, signature):
    payload = build_payload(phone_number_id=NUMBER_A, wa_id="5521998765432", name="X", text="oi")
    response = post_webhook(payload, signature=signature)
    assert response.status_code == 401
    assert InboundWebhookEvent.objects.count() == 0


def test_signature_is_checked_on_raw_bytes(account_a, client):
    body = json.dumps({"entry": []}).encode()
    tampered = body + b" "
    response = client.post(
        WEBHOOK,
        data=tampered,
        content_type="application/json",
        headers={"X-Hub-Signature-256": sign(body, settings.WHATSAPP_APP_SECRET)},
    )
    assert response.status_code == 401


# ------------------------------------------------------------------ ingestão


def test_inbound_text_creates_conversation_and_message(tenant_a, account_a, inbound):
    response = inbound("Bom dia, tenho audiência?")
    assert response.status_code == 200

    event = InboundWebhookEvent.objects.get()
    assert event.processed_at is not None
    with tenant_context(tenant_a.tenant.id):
        conversation = Conversation.objects.get()
        message = Message.objects.get()
    assert conversation.wa_id == "5521998765432"
    assert conversation.contact_name == "Maria"
    assert conversation.unread_count == 1
    assert conversation.last_inbound_at is not None
    assert message.body == "Bom dia, tenho audiência?"
    assert message.direction == Message.Direction.INBOUND
    assert message.status == Message.Status.RECEIVED


def test_same_message_delivered_twice_is_stored_once(tenant_a, account_a, post_webhook):
    payload = build_payload(phone_number_id=NUMBER_A, wa_id="5521998765432", name="M", text="oi")
    assert post_webhook(payload).status_code == 200
    assert post_webhook(payload).status_code == 200

    assert InboundWebhookEvent.objects.count() == 2
    with tenant_context(tenant_a.tenant.id):
        assert Message.objects.count() == 1
        assert Conversation.objects.get().unread_count == 1


def test_reprocessing_an_event_is_a_noop(tenant_a, account_a, inbound):
    from apps.whatsapp.services import process_event

    inbound()
    process_event(InboundWebhookEvent.objects.get().id)
    with tenant_context(tenant_a.tenant.id):
        assert Message.objects.count() == 1


def test_unknown_phone_number_is_ignored(tenant_a, account_a, inbound):
    assert inbound(number="999999").status_code == 200
    assert InboundWebhookEvent.objects.get().processed_at is not None
    with tenant_context(tenant_a.tenant.id):
        assert Message.objects.count() == 0


def test_each_number_routes_to_its_tenant(tenant_a, tenant_b, account_a, account_b, inbound):
    inbound("para A", number=NUMBER_A)
    inbound("para B", number=NUMBER_B, wa_id="5521911112222")

    with tenant_context(tenant_a.tenant.id):
        assert [m.body for m in Message.objects.all()] == ["para A"]
    with tenant_context(tenant_b.tenant.id):
        assert [m.body for m in Message.objects.all()] == ["para B"]


def test_media_message_keeps_caption_and_media_id(tenant_a, account_a, post_webhook):
    payload = build_payload(phone_number_id=NUMBER_A, wa_id="5521998765432", name="M", text="x")
    raw = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    raw.pop("text")
    raw.update({"type": "image", "image": {"id": "media-1", "caption": "comprovante"}})
    post_webhook(payload)

    with tenant_context(tenant_a.tenant.id):
        message = Message.objects.get()
    assert (message.type, message.body, message.media_id) == ("image", "comprovante", "media-1")


@pytest.mark.parametrize("wa_id", ["5521998765432", "552198765432"])
def test_links_client_by_phone_with_or_without_ninth_digit(tenant_a, account_a, inbound, wa_id):
    with tenant_context(tenant_a.tenant.id):
        maria = Client.objects.create(name="Maria", phone_e164="+5521998765432")
    inbound(wa_id=wa_id)
    with tenant_context(tenant_a.tenant.id):
        assert Conversation.objects.get().client_id == maria.id


def test_does_not_link_when_phone_is_ambiguous(tenant_a, account_a, inbound):
    with tenant_context(tenant_a.tenant.id):
        Client.objects.create(name="Mãe", phone_e164="+5521998765432")
        Client.objects.create(name="Filho", phone_e164="+5521998765432")
    inbound()
    with tenant_context(tenant_a.tenant.id):
        assert Conversation.objects.get().client_id is None


def test_message_content_never_goes_to_logs(tenant_a, account_a, inbound, caplog):
    secret = "meu CPF é 529.982.247-25 e o processo é sigiloso"
    with caplog.at_level(logging.DEBUG):
        inbound(secret)
    assert caplog.records, "esperava algum log técnico"
    for record in caplog.records:
        assert "529.982.247-25" not in record.getMessage()
        assert "sigiloso" not in record.getMessage()


def test_processing_failure_records_only_exception_type(account_a, monkeypatch):
    from apps.whatsapp import services

    event = InboundWebhookEvent.objects.create(payload={"entry": []})
    monkeypatch.setattr(
        services, "parse_payload", lambda p: (_ for _ in ()).throw(ValueError("conteúdo xyz"))
    )
    conf = process_inbound_event.app.conf
    conf.task_eager_propagates = False
    try:
        result = process_inbound_event.apply(args=[event.id])
    finally:
        conf.task_eager_propagates = True
    assert result.state == "FAILURE"  # esgotou as tentativas (eager executa os retries na hora)
    event.refresh_from_db()
    assert event.processed_at is None
    assert event.last_error == "ValueError"
    assert event.attempts == process_inbound_event.max_retries + 1

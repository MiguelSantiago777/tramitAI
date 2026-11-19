from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core.tenancy import tenant_context
from apps.whatsapp import services
from apps.whatsapp.gateway import GatewayError
from apps.whatsapp.models import Conversation, Message

from .fixtures import NUMBER_A, TOKEN_A, status_payload

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _term_not_auto_sent(monkeypatch):
    """Aqui o assunto é o transporte: o termo de IA fica como rascunho, sem mensagem a mais."""
    from apps.aprovacoes import services as approvals

    monkeypatch.setattr(approvals, "auto_send", lambda draft: False)


URL = "/api/v1/conversations/"


@pytest.fixture
def conversation(tenant_a, account_a, inbound, login):
    inbound()
    login(tenant_a.owner.email)
    with tenant_context(tenant_a.tenant.id):
        return Conversation.objects.get()


@pytest.fixture
def reply(api_client, django_capture_on_commit_callbacks):
    def _reply(conversation, body="Olá! O advogado vai verificar e já retorna."):
        with django_capture_on_commit_callbacks(execute=True):
            return api_client.post(
                f"{URL}{conversation.id}/messages/", {"body": body}, format="json"
            )

    return _reply


def _message(tenant, **filters):
    with tenant_context(tenant.tenant.id):
        return Message.objects.get(direction=Message.Direction.OUTBOUND, **filters)


def test_manual_reply_is_sent_through_gateway(tenant_a, conversation, reply, fake_gateway):
    response = reply(conversation)
    assert response.status_code == 201
    assert response.json()["status"] == "QUEUED"

    message = _message(tenant_a)
    assert message.status == Message.Status.SENT
    assert message.wa_message_id.startswith("wamid.fake.")
    assert message.sent_by == tenant_a.owner
    assert len(fake_gateway.sent) == 1
    assert fake_gateway.sent[0].to == "5521998765432"
    assert fake_gateway.sent[0].phone_number_id == NUMBER_A


def test_reply_blocked_when_24h_window_is_closed(tenant_a, conversation, reply, fake_gateway):
    with tenant_context(tenant_a.tenant.id):
        Conversation.objects.update(last_inbound_at=timezone.now() - timedelta(hours=25))
    response = reply(conversation)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "window_closed"
    assert fake_gateway.sent == []


def test_empty_reply_is_rejected(conversation, reply):
    assert reply(conversation, body="   ").status_code == 400


def test_definitive_error_marks_failed_without_retry(tenant_a, conversation, reply, fake_gateway):
    fake_gateway.fail_next = GatewayError("131026", "Número sem WhatsApp", retryable=False)
    reply(conversation)
    message = _message(tenant_a)
    assert message.status == Message.Status.FAILED
    assert message.error_detail == "Número sem WhatsApp"
    assert fake_gateway.sent == []


def test_uncertain_send_is_not_retried(tenant_a, conversation, reply, fake_gateway):
    fake_gateway.fail_next = GatewayError("uncertain", "ReadTimeout", retryable=False)
    reply(conversation)
    message = _message(tenant_a)
    assert message.status == Message.Status.FAILED
    assert "Verifique no WhatsApp antes de reenviar" in message.error_detail
    assert fake_gateway.sent == []


def test_retryable_error_keeps_message_queued_and_next_attempt_sends(
    tenant_a, conversation, fake_gateway
):
    with tenant_context(tenant_a.tenant.id):
        message = Message.objects.create(
            conversation=conversation,
            direction=Message.Direction.OUTBOUND,
            body="x",
            status=Message.Status.QUEUED,
        )
    fake_gateway.fail_next = GatewayError("429", "rate limit", retryable=True)
    with pytest.raises(services.RetryableSendError):
        services.deliver_outbound(tenant_a.tenant.id, message.id)
    assert _message(tenant_a).status == Message.Status.QUEUED

    services.deliver_outbound(tenant_a.tenant.id, message.id)
    assert _message(tenant_a).status == Message.Status.SENT
    assert len(fake_gateway.sent) == 1


def test_task_retries_then_gives_up(tenant_a, conversation, fake_gateway):
    from apps.whatsapp.tasks import send_message

    with tenant_context(tenant_a.tenant.id):
        message = Message.objects.create(
            conversation=conversation,
            direction=Message.Direction.OUTBOUND,
            body="x",
            status=Message.Status.QUEUED,
        )
    args = [str(tenant_a.tenant.id), str(message.id)]

    # Última tentativa: desiste e marca FAILED, sem enviar.
    fake_gateway.fail_next = GatewayError("429", "rate limit", retryable=True)
    send_message.apply(args=args, retries=send_message.max_retries, throw=False)
    assert _message(tenant_a).status == Message.Status.FAILED
    assert fake_gateway.sent == []


def test_task_retry_sends_after_transient_error(tenant_a, conversation, fake_gateway):
    from apps.whatsapp.tasks import send_message

    with tenant_context(tenant_a.tenant.id):
        message = Message.objects.create(
            conversation=conversation,
            direction=Message.Direction.OUTBOUND,
            body="x",
            status=Message.Status.QUEUED,
        )
    fake_gateway.fail_next = GatewayError("429", "rate limit", retryable=True)
    # Em modo eager o Celery executa o retry na hora.
    result = send_message.apply(args=[str(tenant_a.tenant.id), str(message.id)], throw=False)
    assert result.state == "SUCCESS"
    assert _message(tenant_a).status == Message.Status.SENT
    assert len(fake_gateway.sent) == 1


def test_duplicate_task_does_not_send_twice(tenant_a, conversation, reply, fake_gateway):
    reply(conversation)
    message = _message(tenant_a)
    services.deliver_outbound(tenant_a.tenant.id, message.id)
    assert len(fake_gateway.sent) == 1


def test_stuck_sending_becomes_failed(tenant_a, conversation):
    with tenant_context(tenant_a.tenant.id):
        message = Message.objects.create(
            conversation=conversation,
            direction=Message.Direction.OUTBOUND,
            body="x",
            status=Message.Status.SENDING,
        )
        Message.objects.filter(pk=message.pk).update(
            updated_at=timezone.now() - timedelta(minutes=10)
        )
    assert services.fail_stuck_sending() == 1
    assert _message(tenant_a).status == Message.Status.FAILED


def test_status_updates_never_go_backwards(tenant_a, conversation, reply, post_webhook):
    reply(conversation)
    wamid = _message(tenant_a).wa_message_id

    post_webhook(status_payload(NUMBER_A, wamid, "read", ts=1_700_000_200))
    post_webhook(status_payload(NUMBER_A, wamid, "delivered", ts=1_700_000_100))

    message = _message(tenant_a)
    assert message.status == Message.Status.READ
    assert message.read_at is not None
    assert message.delivered_at is not None


def test_failed_status_from_meta(tenant_a, conversation, reply, post_webhook):
    reply(conversation)
    wamid = _message(tenant_a).wa_message_id
    post_webhook(status_payload(NUMBER_A, wamid, "failed"))

    message = _message(tenant_a)
    assert message.status == Message.Status.FAILED
    assert message.error_code == "131047"


# ------------------------------------------------------------------ inbox API


def test_list_shows_preview_unread_and_window(conversation, api_client):
    body = api_client.get(URL).json()
    assert body["count"] == 1
    item = body["results"][0]
    assert item["unread_count"] == 1
    assert item["window_open"] is True
    assert item["last_message"]["direction"] == "IN"
    assert item["last_message"]["preview"] == "Oi, queria saber do meu processo"
    assert item["phone"] == "+5521998765432"


def test_messages_are_listed_newest_first(conversation, reply, api_client):
    reply(conversation)
    results = api_client.get(f"{URL}{conversation.id}/messages/").json()["results"]
    assert [m["direction"] for m in results] == ["OUT", "IN"]
    assert results[0]["sent_by_name"]


def test_read_resets_unread(conversation, api_client):
    assert api_client.post(f"{URL}{conversation.id}/read/").status_code == 204
    assert api_client.get(f"{URL}{conversation.id}/").json()["unread_count"] == 0


def test_link_client_and_close(conversation, api_client):
    client_id = api_client.post("/api/v1/clients/", {"name": "Maria"}, format="json").json()["id"]
    response = api_client.patch(
        f"{URL}{conversation.id}/", {"client_id": client_id, "status": "CLOSED"}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["client_name"] == "Maria"
    assert response.json()["status"] == "CLOSED"


def test_cannot_link_client_from_other_tenant(tenant_b, conversation, api_client, login):
    login(tenant_b.owner.email)
    foreign = api_client.post("/api/v1/clients/", {"name": "Do B"}, format="json").json()["id"]
    login(conversation.tenant.memberships.first().user.email)
    response = api_client.patch(f"{URL}{conversation.id}/", {"client_id": foreign}, format="json")
    assert response.status_code == 400


def test_other_tenant_cannot_see_or_reply(tenant_b, conversation, api_client, login, reply):
    login(tenant_b.owner.email)
    assert api_client.get(URL).json()["count"] == 0
    assert api_client.get(f"{URL}{conversation.id}/").status_code == 404
    assert reply(conversation).status_code == 404


def test_access_token_never_leaves_the_api(conversation, reply, api_client):
    reply(conversation)
    for path in (URL, f"{URL}{conversation.id}/", f"{URL}{conversation.id}/messages/"):
        assert TOKEN_A not in api_client.get(path).content.decode()


def test_token_is_encrypted_at_rest(tenant_a, account_a):
    assert TOKEN_A not in account_a.access_token_encrypted

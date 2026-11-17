"""WhatsApp via ponte Baileys: webhook assinado, sessão por escritório e envio sem janela."""

import json
from datetime import timedelta
from typing import Any

import httpx
import pytest
from django.utils import timezone

from apps.accounts.models import Membership, User
from apps.aprovacoes.models import OutboundDraft
from apps.core.tenancy import tenant_atomic, tenant_context
from apps.whatsapp import services
from apps.whatsapp.gateway import Credentials, GatewayError
from apps.whatsapp.gateway import bridge as bridge_module
from apps.whatsapp.gateway.bridge import BridgeGateway, SessionInfo
from apps.whatsapp.models import Conversation, Message, WhatsAppAccount
from apps.whatsapp.signature import sign

WEBHOOK = "/api/webhooks/bridge/"
CONNECTION = "/api/v1/whatsapp/connection/"


@pytest.fixture
def baileys_a(tenant_a: Any) -> WhatsAppAccount:
    with tenant_atomic(tenant_a.tenant.id):
        return services.ensure_baileys_account(tenant_id=tenant_a.tenant.id, user=tenant_a.owner)


@pytest.fixture
def post_bridge(client: Any, settings: Any, django_capture_on_commit_callbacks: Any) -> Any:
    def _post(payload: dict[str, Any], *, secret: str | None = None) -> Any:
        body = json.dumps(payload).encode()
        signature = sign(body, secret or settings.WHATSAPP_BRIDGE_SECRET)
        with django_capture_on_commit_callbacks(execute=True):
            return client.post(
                WEBHOOK,
                data=body,
                content_type="application/json",
                headers={"X-Bridge-Signature": signature},
            )

    return _post


def _message(session: str, text: str = "Oi, tudo bem?", msg_id: str = "3EB0AAA") -> dict:
    return {
        "session_id": session,
        "event": "messages",
        "messages": [
            {
                "id": msg_id,
                "from": "5521998765432",
                "name": "Maria",
                "timestamp": 1_763_400_000,
                "type": "text",
                "text": text,
            }
        ],
    }


def test_webhook_rejects_wrong_signature(post_bridge, baileys_a):
    response = post_bridge(_message(baileys_a.phone_number_id), secret="outro-segredo")
    assert response.status_code == 401


def test_inbound_message_creates_conversation_and_is_idempotent(tenant_a, baileys_a, post_bridge):
    assert post_bridge(_message(baileys_a.phone_number_id)).status_code == 200
    post_bridge(_message(baileys_a.phone_number_id))  # a ponte reenviou

    with tenant_context(tenant_a.tenant.id):
        [message] = Message.objects.all()
        conversation = Conversation.objects.get()
        offered = OutboundDraft.objects.filter(origin=OutboundDraft.Origin.TERM_REQUEST).count()
    assert message.wa_message_id == "bl:3EB0AAA"
    assert message.body == "Oi, tudo bem?"
    assert conversation.wa_id == "5521998765432"
    assert conversation.contact_name == "Maria"
    assert offered == 1  # passou pelo mesmo fluxo da Meta (termo de ciência)


def test_session_of_other_tenant_never_leaks(tenant_a, tenant_b, baileys_a, post_bridge):
    post_bridge(_message(baileys_a.phone_number_id))
    with tenant_context(tenant_b.tenant.id):
        assert Message.objects.count() == 0


def test_connection_event_updates_account(tenant_a, baileys_a, post_bridge):
    post_bridge(
        {
            "session_id": baileys_a.phone_number_id,
            "event": "connection",
            "status": "open",
            "phone": "5521912345678",
        }
    )
    with tenant_context(tenant_a.tenant.id):
        account = WhatsAppAccount.objects.get()
    assert account.connection == WhatsAppAccount.Connection.CONNECTED
    assert account.display_phone == "+5521912345678"


def test_window_never_closes_and_reply_goes_through_bridge(
    tenant_a, baileys_a, post_bridge, fake_gateway
):
    post_bridge(_message(baileys_a.phone_number_id))
    with tenant_atomic(tenant_a.tenant.id):
        conversation = Conversation.objects.select_related("account").get()
        Conversation.objects.filter(pk=conversation.pk).update(
            last_inbound_at=timezone.now() - timedelta(days=10)
        )
        conversation.refresh_from_db()
        assert services.window_open(conversation)
        message = services.queue_text(conversation=conversation, body="Olá!", sent_by=None)
    services.deliver_outbound(tenant_a.tenant.id, message.pk)

    assert fake_gateway.sent[-1].body == "Olá!"
    assert fake_gateway.sent[-1].phone_number_id == baileys_a.phone_number_id


def test_status_from_bridge_updates_outbound(tenant_a, baileys_a, post_bridge):
    post_bridge(_message(baileys_a.phone_number_id))
    with tenant_atomic(tenant_a.tenant.id):
        conversation = Conversation.objects.get()
        Message.objects.create(
            conversation=conversation,
            direction=Message.Direction.OUTBOUND,
            wa_message_id="bl:OUT1",
            body="x",
            status=Message.Status.SENT,
        )
    post_bridge(
        {
            "session_id": baileys_a.phone_number_id,
            "event": "statuses",
            "statuses": [{"id": "OUT1", "status": "read", "timestamp": 1_763_400_100}],
        }
    )
    with tenant_context(tenant_a.tenant.id):
        assert Message.objects.get(wa_message_id="bl:OUT1").status == Message.Status.READ


def test_tenant_with_cloud_api_cannot_create_baileys(tenant_a, account_a):
    from apps.core.exceptions import ApiError

    with tenant_atomic(tenant_a.tenant.id), pytest.raises(ApiError) as exc:
        services.ensure_baileys_account(tenant_id=tenant_a.tenant.id, user=tenant_a.owner)
    assert exc.value.error_code == "cloud_api_in_use"


# --------------------------------------------------------------------------- gateway HTTP


def _gateway(handler: Any) -> BridgeGateway:
    return BridgeGateway(
        client=httpx.Client(base_url="http://bridge.test", transport=httpx.MockTransport(handler))
    )


CREDS = Credentials(phone_number_id="bl-abc123", access_token="")


def test_gateway_sends_and_prefixes_id():
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "3EB0XYZ"})

    result = _gateway(handler).send_text(CREDS, to="5521998765432", body="Olá")
    assert result.wa_message_id == "bl:3EB0XYZ"
    assert seen == {
        "path": "/sessions/bl-abc123/messages",
        "json": {"to": "5521998765432", "text": "Olá"},
    }


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (409, "not_connected", True),
        (503, "lookup_failed", True),
        (422, "not_on_whatsapp", False),
        (500, "internal", False),
    ],
)
def test_gateway_errors(status, code, retryable):
    gateway = _gateway(lambda r: httpx.Response(status, json={"error": code}))
    with pytest.raises(GatewayError) as exc:
        gateway.send_text(CREDS, to="1", body="x")
    assert exc.value.code == code
    assert exc.value.retryable is retryable


def test_gateway_connect_error_is_retryable_and_timeout_is_not():
    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(GatewayError) as down:
        _gateway(refused).send_text(CREDS, to="1", body="x")
    assert down.value.retryable is True
    with pytest.raises(GatewayError) as unsure:
        _gateway(slow).send_text(CREDS, to="1", body="x")
    assert (unsure.value.code, unsure.value.retryable) == ("uncertain", False)


# --------------------------------------------------------------------------- API de conexão


@pytest.fixture
def fake_bridge(monkeypatch: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "started": [],
        "logged_out": [],
        "info": SessionInfo("qr", "data:qr", None),
    }
    monkeypatch.setattr(
        bridge_module, "start_session", lambda sid: state["started"].append(sid) or state["info"]
    )
    monkeypatch.setattr(bridge_module, "session_info", lambda sid: state["info"])
    monkeypatch.setattr(
        bridge_module, "logout_session", lambda sid: state["logged_out"].append(sid)
    )
    return state


def test_connection_not_configured(tenant_a, login, api_client):
    login(tenant_a.owner.email)
    data = api_client.get(CONNECTION).json()
    assert data["status"] == "not_configured"
    assert data["can_manage"] is True


def test_owner_connects_and_sees_qr(tenant_a, login, api_client, fake_bridge):
    login(tenant_a.owner.email)
    data = api_client.post(CONNECTION).json()
    assert data["provider"] == "BAILEYS"
    assert data["status"] == "qr"
    assert data["qr"] == "data:qr"
    assert len(fake_bridge["started"]) == 1

    # Conectar de novo reaproveita a mesma sessão.
    api_client.post(CONNECTION)
    assert len(set(fake_bridge["started"])) == 1


def test_only_owner_pairs_and_others_never_see_qr(
    tenant_a, baileys_a, login, api_client, fake_bridge
):
    lawyer = User.objects.create_user(email="adv@a.test", password="senha-de-teste-123")
    Membership.objects.create(user=lawyer, tenant=tenant_a.tenant, role=Membership.Role.LAWYER)
    login("adv@a.test")
    assert api_client.post(CONNECTION).status_code == 403
    assert api_client.delete(CONNECTION).status_code == 403
    data = api_client.get(CONNECTION).json()
    assert data["status"] == "qr"
    assert data["qr"] is None
    assert data["can_manage"] is False


def test_connected_and_disconnect(tenant_a, baileys_a, login, api_client, fake_bridge):
    fake_bridge["info"] = SessionInfo("open", None, "5521912345678")
    login(tenant_a.owner.email)
    data = api_client.get(CONNECTION).json()
    assert (data["status"], data["phone"]) == ("connected", "+5521912345678")

    fake_bridge["info"] = SessionInfo("not_started", None, None)
    data = api_client.delete(CONNECTION).json()
    assert fake_bridge["logged_out"] == [baileys_a.phone_number_id]
    assert data["status"] == "disconnected"
    with tenant_context(tenant_a.tenant.id):
        assert WhatsAppAccount.objects.get().connection == WhatsAppAccount.Connection.LOGGED_OUT


def test_bridge_down_is_reported(tenant_a, baileys_a, login, api_client, monkeypatch):
    def down(sid: str) -> SessionInfo:
        raise bridge_module.BridgeUnavailable("ConnectError")

    monkeypatch.setattr(bridge_module, "session_info", down)
    login(tenant_a.owner.email)
    assert api_client.get(CONNECTION).json()["status"] == "bridge_down"

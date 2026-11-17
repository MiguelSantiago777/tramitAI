import json
from typing import Any

import httpx
import pytest

from apps.core.br import whatsapp_phone_candidates
from apps.core.crypto import DecryptionError, decrypt_secret, encrypt_secret
from apps.whatsapp.gateway import Credentials, GatewayError
from apps.whatsapp.gateway.cloud_api import CloudApiGateway

CREDS = Credentials(phone_number_id="123", access_token="tok")


def _gateway(handler):
    return CloudApiGateway(client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_send_text_builds_request_and_returns_wamid(settings):
    settings.WHATSAPP_GRAPH_VERSION = "v24.0"
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["Authorization"]
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={"messages": [{"id": "wamid.ABC"}]})

    result = _gateway(handler).send_text(CREDS, to="5521998765432", body="Olá")
    assert result.wa_message_id == "wamid.ABC"
    assert seen["url"] == "https://graph.facebook.com/v24.0/123/messages"
    assert seen["auth"] == "Bearer tok"
    assert seen["json"]["to"] == "5521998765432"
    assert seen["json"]["text"] == {"preview_url": False, "body": "Olá"}


def test_meta_error_is_definitive():
    def handler(request):
        return httpx.Response(
            400, json={"error": {"code": 131030, "message": "Recipient not in allowed list"}}
        )

    with pytest.raises(GatewayError) as info:
        _gateway(handler).send_text(CREDS, to="1", body="x")
    assert info.value.code == "131030"
    assert info.value.retryable is False


def test_rate_limit_is_retryable():
    with pytest.raises(GatewayError) as info:
        _gateway(lambda r: httpx.Response(429, json={"error": {"code": 130429}})).send_text(
            CREDS, to="1", body="x"
        )
    assert info.value.retryable is True


def test_connect_error_is_retryable():
    def handler(request):
        raise httpx.ConnectError("recusado", request=request)

    with pytest.raises(GatewayError) as info:
        _gateway(handler).send_text(CREDS, to="1", body="x")
    assert info.value.retryable is True


def test_read_timeout_is_uncertain_and_not_retryable():
    def handler(request):
        raise httpx.ReadTimeout("demorou", request=request)

    with pytest.raises(GatewayError) as info:
        _gateway(handler).send_text(CREDS, to="1", body="x")
    assert info.value.code == "uncertain"
    assert info.value.retryable is False


def test_secret_roundtrip_and_wrong_key(settings):
    token = encrypt_secret("segredo")
    assert token != "segredo"
    assert decrypt_secret(token) == "segredo"

    settings.FIELD_ENCRYPTION_KEYS = ["b3V0cmEtY2hhdmUtb3V0cmEtY2hhdmUtb3V0cmEtMTI="]
    with pytest.raises(DecryptionError):
        decrypt_secret(token)


def test_key_rotation_keeps_old_tokens_readable(settings):
    old_key = settings.FIELD_ENCRYPTION_KEYS[0]
    token = encrypt_secret("segredo")
    settings.FIELD_ENCRYPTION_KEYS = ["b3V0cmEtY2hhdmUtb3V0cmEtY2hhdmUtb3V0cmEtMTI=", old_key]
    assert decrypt_secret(token) == "segredo"


@pytest.mark.parametrize(
    ("wa_id", "expected"),
    [
        ("5521998765432", ["+5521998765432", "+552198765432"]),
        ("552198765432", ["+552198765432", "+5521998765432"]),
        ("552134567890", ["+552134567890"]),  # fixo: sem variação
        ("14155550100", ["+14155550100"]),
    ],
)
def test_whatsapp_phone_candidates(wa_id, expected):
    assert whatsapp_phone_candidates(wa_id) == expected

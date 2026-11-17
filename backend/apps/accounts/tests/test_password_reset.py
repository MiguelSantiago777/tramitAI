import re

from django.core import mail

REQUEST = "/api/v1/auth/password-reset/"
CONFIRM = "/api/v1/auth/password-reset/confirm/"


def _request(api_client, email, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        return api_client.post(REQUEST, {"email": email}, format="json")


def _link_params(body: str) -> dict[str, str]:
    match = re.search(r"/redefinir-senha\?uid=([^&\s]+)&token=(\S+)", body)
    assert match, body
    return {"uid": match.group(1), "token": match.group(2)}


def test_reset_flow_changes_password_and_link_is_single_use(
    tenant_a, api_client, login, django_capture_on_commit_callbacks
):
    response = _request(
        api_client, tenant_a.owner.email.upper(), django_capture_on_commit_callbacks
    )
    assert response.status_code == 204
    [email] = mail.outbox
    assert email.to == [tenant_a.owner.email]
    assert "https://app.tramitai.test/redefinir-senha?uid=" in email.body
    params = _link_params(str(email.body))

    ok = api_client.post(CONFIRM, {**params, "password": "nova-senha-bem-forte-42"}, format="json")
    assert ok.status_code == 204
    assert login(tenant_a.owner.email, password="nova-senha-bem-forte-42").status_code == 200

    again = api_client.post(CONFIRM, {**params, "password": "outra-senha-forte-77"}, format="json")
    assert again.status_code == 400
    assert again.json()["error"]["code"] == "invalid_reset_link"


def test_unknown_email_looks_the_same_and_sends_nothing(
    tenant_a, api_client, django_capture_on_commit_callbacks
):
    response = _request(api_client, "ninguem@nada.test", django_capture_on_commit_callbacks)
    assert response.status_code == 204
    assert mail.outbox == []


def test_weak_password_is_rejected(tenant_a, api_client, django_capture_on_commit_callbacks):
    _request(api_client, tenant_a.owner.email, django_capture_on_commit_callbacks)
    params = _link_params(str(mail.outbox[0].body))
    response = api_client.post(CONFIRM, {**params, "password": "123"}, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "weak_password"


def test_tampered_token_is_rejected(tenant_a, api_client, django_capture_on_commit_callbacks):
    _request(api_client, tenant_a.owner.email, django_capture_on_commit_callbacks)
    params = _link_params(str(mail.outbox[0].body))
    response = api_client.post(
        CONFIRM, {"uid": params["uid"], "token": "abc-123", "password": "x" * 20}, format="json"
    )
    assert response.json()["error"]["code"] == "invalid_reset_link"

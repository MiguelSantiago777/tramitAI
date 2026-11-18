"""Documentos: upload validado, pasta do cliente, download com login e mídia do WhatsApp."""

import json
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import Membership, User
from apps.clientes.models import Client
from apps.core.tenancy import tenant_atomic, tenant_context
from apps.documentos.models import Document
from apps.documentos.services import safe_filename
from apps.whatsapp import services as wa_services
from apps.whatsapp.gateway import GatewayError, MediaFile
from apps.whatsapp.models import Conversation, Message
from apps.whatsapp.signature import sign

DOCS = "/api/v1/documents/"
PDF = b"%PDF-1.4 conteudo de teste"


def _pdf(name: str = "rg.pdf", content: bytes = PDF) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content, content_type="application/pdf")


@pytest.fixture
def client_a(tenant_a: Any) -> Client:
    with tenant_context(tenant_a.tenant.id):
        return Client.objects.create(name="Ana Souza", phone_e164="+5521998765432")


def _upload(api_client: Any, **data: Any) -> Any:
    return api_client.post(DOCS, data, format="multipart")


def test_upload_list_download_and_timeline(tenant_a, client_a, login, api_client):
    login(tenant_a.owner.email)
    created = _upload(
        api_client, file=_pdf(), client_id=str(client_a.pk), category="PESSOAL", description="RG"
    )
    assert created.status_code == 201, created.content
    doc = created.json()
    assert doc["name"] == "rg.pdf"
    assert doc["content_type"] == "application/pdf"
    assert doc["size"] == len(PDF)
    assert doc["client_name"] == "Ana Souza"
    assert doc["can_preview"] is True

    listed = api_client.get(f"{DOCS}?client={client_a.pk}").json()["results"]
    assert [d["id"] for d in listed] == [doc["id"]]

    download = api_client.get(f"{DOCS}{doc['id']}/download/")
    assert download.status_code == 200
    assert b"".join(download.streaming_content) == PDF
    assert "attachment" in download["Content-Disposition"]
    assert download["X-Content-Type-Options"] == "nosniff"
    inline = api_client.get(f"{DOCS}{doc['id']}/download/?inline=1")
    assert inline["Content-Type"] == "application/pdf"
    assert "inline" in inline["Content-Disposition"]

    timeline = api_client.get(f"/api/v1/clients/{client_a.pk}/timeline/").json()
    assert any(i["type"] == "document" and i["body"] == "rg.pdf" for i in timeline["results"])


@pytest.mark.parametrize(
    ("name", "content", "code"),
    [
        ("virus.exe", b"MZ...", "file_type_not_allowed"),
        ("pagina.html", b"<script>", "file_type_not_allowed"),
        ("desenho.svg", b"<svg/>", "file_type_not_allowed"),
        ("falso.pdf", b"<html>nao sou pdf", "file_type_mismatch"),
        ("vazio.pdf", b"", "empty_file"),
    ],
)
def test_upload_rejects_unsafe_files(tenant_a, client_a, login, api_client, name, content, code):
    login(tenant_a.owner.email)
    upload = SimpleUploadedFile(name, content)
    response = _upload(api_client, file=upload, client_id=str(client_a.pk))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == code


def test_upload_size_limit(tenant_a, client_a, login, api_client, settings):
    settings.DOCUMENT_MAX_BYTES = 10
    login(tenant_a.owner.email)
    response = _upload(api_client, file=_pdf(), client_id=str(client_a.pk))
    assert response.status_code == 413


def test_upload_needs_client_or_case(tenant_a, login, api_client):
    login(tenant_a.owner.email)
    response = _upload(api_client, file=_pdf())
    assert response.json()["error"]["code"] == "document_owner"


def test_other_office_cannot_see_or_download(tenant_a, tenant_b, client_a, login, api_client):
    login(tenant_a.owner.email)
    doc = _upload(api_client, file=_pdf(), client_id=str(client_a.pk)).json()
    api_client.credentials()
    login(tenant_b.owner.email)
    assert api_client.get(f"{DOCS}{doc['id']}/download/").status_code == 404
    assert api_client.get(DOCS).json()["results"] == []
    other = _upload(api_client, file=_pdf(), client_id=str(client_a.pk))
    assert other.status_code == 400  # cliente de outro escritório não existe aqui


def test_staff_uploads_but_cannot_delete(tenant_a, client_a, login, api_client):
    staff = User.objects.create_user(email="equipe@a.test", password="senha-de-teste-123")
    Membership.objects.create(user=staff, tenant=tenant_a.tenant, role=Membership.Role.STAFF)
    login("equipe@a.test")
    doc = _upload(api_client, file=_pdf(), client_id=str(client_a.pk)).json()
    assert api_client.delete(f"{DOCS}{doc['id']}/").status_code == 403

    api_client.credentials()
    login(tenant_a.owner.email)
    renamed = api_client.patch(f"{DOCS}{doc['id']}/", {"name": "../RG frente.pdf"}, format="json")
    assert renamed.json()["name"] == "RG frente.pdf"
    assert api_client.delete(f"{DOCS}{doc['id']}/").status_code == 204
    with tenant_context(tenant_a.tenant.id):
        assert not Document.objects.exists()


def test_safe_filename():
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename('C:\\Users\\x\\"nota".pdf') == "nota.pdf"
    assert safe_filename("   ") == "arquivo"
    assert len(safe_filename("a" * 400 + ".pdf")) == 200


# ---------------------------------------------------------------- mídia do WhatsApp


def _media_payload(number: str, *, media_id: str = "media-123") -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": number},
                            "contacts": [{"profile": {"name": "Ana"}, "wa_id": "5521998765432"}],
                            "messages": [
                                {
                                    "from": "5521998765432",
                                    "id": f"wamid.{media_id}",
                                    "timestamp": "1763400000",
                                    "type": "document",
                                    "document": {
                                        "id": media_id,
                                        "filename": "contracheque.pdf",
                                        "caption": "segue",
                                    },
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def test_whatsapp_media_is_stored_and_shows_on_client_after_link(
    tenant_a, account_a, post_webhook, fake_gateway, login, api_client
):
    fake_gateway.media["media-123"] = MediaFile(PDF, "application/pdf")
    post_webhook(_media_payload(account_a.phone_number_id))

    with tenant_context(tenant_a.tenant.id):
        doc = Document.objects.get()
        message = Message.objects.get(type="document")
        conversation = Conversation.objects.get()
    assert doc.name == "contracheque.pdf"
    assert doc.source == Document.Source.WHATSAPP
    assert doc.message_id == message.pk
    assert doc.client_id is None
    assert doc.description == "segue"
    assert doc.file.read() == PDF

    login(tenant_a.owner.email)
    messages = api_client.get(f"/api/v1/conversations/{conversation.pk}/messages/").json()
    item = next(m for m in messages["results"] if m["type"] == "document")
    assert item["document"]["name"] == "contracheque.pdf"
    assert item["media_pending"] is False

    # Contato vira cliente depois: o arquivo aparece na pasta dele.
    with tenant_atomic(tenant_a.tenant.id):
        ana = Client.objects.create(name="Ana", phone_e164="+5521998765432")
        Conversation.objects.filter(pk=conversation.pk).update(client=ana)
    listed = api_client.get(f"{DOCS}?client={ana.pk}").json()["results"]
    assert [d["name"] for d in listed] == ["contracheque.pdf"]


def test_whatsapp_media_permanent_failure_marks_message(
    tenant_a, account_a, post_webhook, fake_gateway
):
    fake_gateway.fail_next = GatewayError("131052", "expirada", retryable=False)
    post_webhook(_media_payload(account_a.phone_number_id))
    with tenant_context(tenant_a.tenant.id):
        message = Message.objects.get(type="document")
        assert not Document.objects.exists()
    assert message.error_code == "131052"
    assert "reenviar" in message.error_detail


def test_bridge_media_too_large_is_not_downloaded(
    tenant_a, client, settings, django_capture_on_commit_callbacks, fake_gateway
):
    with tenant_atomic(tenant_a.tenant.id):
        account = wa_services.ensure_baileys_account(
            tenant_id=tenant_a.tenant.id, user=tenant_a.owner
        )
    payload = {
        "session_id": account.phone_number_id,
        "event": "messages",
        "messages": [
            {
                "id": "3EBBIG",
                "from": "5521998765432",
                "timestamp": 1_763_400_000,
                "type": "video",
                "text": "",
                "media": {"mimetype": "video/mp4", "size": 999_999_999, "error": "too_large"},
            },
            {
                "id": "3EBFOTO",
                "from": "5521998765432",
                "timestamp": 1_763_400_001,
                "type": "image",
                "text": "",
                "media": {"mimetype": "image/jpeg", "size": 10},
            },
        ],
    }
    fake_gateway.media["3EBFOTO"] = MediaFile(b"\xff\xd8\xff foto", "image/jpeg")
    body = json.dumps(payload).encode()
    with django_capture_on_commit_callbacks(execute=True):
        client.post(
            "/api/webhooks/bridge/",
            data=body,
            content_type="application/json",
            headers={"X-Bridge-Signature": sign(body, settings.WHATSAPP_BRIDGE_SECRET)},
        )
    with tenant_context(tenant_a.tenant.id):
        big = Message.objects.get(type="video")
        doc = Document.objects.get()
    assert big.error_code == "too_large"
    assert "grande demais" in big.error_detail
    assert doc.content_type == "image/jpeg"
    assert doc.name.endswith(".jpg")
    assert "3EBFOTO" in fake_gateway.released

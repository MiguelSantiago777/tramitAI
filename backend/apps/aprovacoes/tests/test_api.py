from datetime import timedelta

import pytest
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from apps.accounts.models import Membership, User
from apps.aprovacoes.models import OutboundDraft
from apps.clientes.models import Client
from apps.clientes.services import register_term_acceptance
from apps.core.models import AuditEvent
from apps.core.tenancy import tenant_context
from apps.tenants.models import TenantSettings
from apps.whatsapp.gateway import GatewayError
from apps.whatsapp.models import Conversation, Message

pytestmark = pytest.mark.django_db

URL = "/api/v1/drafts/"


@pytest.fixture
def pending(tenant_a, account_a, inbound, drafts, fake_llm, login):
    """Cliente com aceite presencial manda mensagem → rascunho da IA pendente."""
    with tenant_context(tenant_a.tenant.id):
        maria = Client.objects.create(name="Maria", phone_e164="+5521998765432")
        register_term_acceptance(client=maria, channel="IN_PERSON")
    inbound("Tem novidade no processo?")
    login(tenant_a.owner.email)
    [draft] = drafts(origin=OutboundDraft.Origin.AI_REPLY)
    return draft


def _post(api_client, django_capture_on_commit_callbacks, path, body=None):
    with django_capture_on_commit_callbacks(execute=True):
        return api_client.post(path, body or {}, format="json")


def test_list_pending_queue(pending, api_client):
    body = api_client.get(URL, {"status": "DRAFT"}).json()
    assert body["count"] == 1
    item = body["results"][0]
    assert item["origin"] == "AI_REPLY"
    assert item["source_text"] == "Tem novidade no processo?"
    assert item["client_name"] == "Maria"
    assert item["window_open"] is True
    assert item["summary"]


def test_approve_with_edit_sends_and_audits(
    tenant_a, pending, api_client, django_capture_on_commit_callbacks, fake_gateway
):
    response = _post(
        api_client,
        django_capture_on_commit_callbacks,
        f"{URL}{pending.id}/approve/",
        {"body": "Olá, Maria! Vou verificar e te retorno hoje."},
    )
    assert response.status_code == 200

    detail = api_client.get(f"{URL}{pending.id}/").json()
    assert detail["status"] == "SENT"
    assert detail["final_body"] == "Olá, Maria! Vou verificar e te retorno hoje."
    assert detail["decided_by_name"] == tenant_a.owner.email
    assert fake_gateway.sent[-1].body == "Olá, Maria! Vou verificar e te retorno hoje."

    actions = [e["action"] for e in detail["history"]]
    assert actions == ["draft.created", "draft.approved", "draft.sent"]
    approved = detail["history"][1]
    assert approved["actor_type"] == "USER"
    assert approved["data"]["edited"] is True
    # auditoria não guarda o conteúdo da mensagem
    assert "Maria" not in str([e["data"] for e in detail["history"]])


def test_approve_without_edit_keeps_generated_text(
    pending, api_client, django_capture_on_commit_callbacks, fake_gateway
):
    _post(api_client, django_capture_on_commit_callbacks, f"{URL}{pending.id}/approve/")
    assert fake_gateway.sent[-1].body == pending.generated_body


def test_cannot_decide_twice(pending, api_client, django_capture_on_commit_callbacks):
    _post(
        api_client,
        django_capture_on_commit_callbacks,
        f"{URL}{pending.id}/reject/",
        {"reason": "x"},
    )
    response = _post(api_client, django_capture_on_commit_callbacks, f"{URL}{pending.id}/approve/")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "draft_already_decided"


def test_reject_with_reason(pending, api_client, django_capture_on_commit_callbacks, fake_gateway):
    response = _post(
        api_client,
        django_capture_on_commit_callbacks,
        f"{URL}{pending.id}/reject/",
        {"reason": "Vou ligar para a cliente."},
    )
    assert response.json()["status"] == "REJECTED"
    assert response.json()["rejection_reason"] == "Vou ligar para a cliente."
    assert fake_gateway.sent == []


def test_approve_blocked_when_window_closed(
    tenant_a, pending, api_client, django_capture_on_commit_callbacks
):
    with tenant_context(tenant_a.tenant.id):
        Conversation.objects.update(last_inbound_at=timezone.now() - timedelta(hours=30))
    response = _post(api_client, django_capture_on_commit_callbacks, f"{URL}{pending.id}/approve/")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "window_closed"
    assert api_client.get(f"{URL}{pending.id}/").json()["status"] == "DRAFT"


def test_send_failure_marks_draft_failed(
    pending, api_client, django_capture_on_commit_callbacks, fake_gateway
):
    fake_gateway.fail_next = GatewayError("131026", "Número sem WhatsApp", retryable=False)
    _post(api_client, django_capture_on_commit_callbacks, f"{URL}{pending.id}/approve/")
    detail = api_client.get(f"{URL}{pending.id}/").json()
    assert detail["status"] == "FAILED"
    assert detail["failure_detail"] == "Número sem WhatsApp"
    assert detail["history"][-1]["action"] == "draft.failed"


@pytest.mark.parametrize(("flag", "expected"), [(False, 403), (True, 200)])
def test_staff_approval_depends_on_tenant_flag(
    tenant_a, pending, api_client, login, django_capture_on_commit_callbacks, flag, expected
):
    staff = User.objects.create_user(email="equipe@a.test", password="senha-de-teste-123")
    Membership.objects.create(user=staff, tenant=tenant_a.tenant, role=Membership.Role.STAFF)
    with tenant_context(tenant_a.tenant.id):
        TenantSettings.objects.update(staff_can_approve=flag)
    login("equipe@a.test")
    response = _post(api_client, django_capture_on_commit_callbacks, f"{URL}{pending.id}/approve/")
    assert response.status_code == expected


def test_other_tenant_cannot_see_or_decide(
    tenant_b, pending, api_client, login, django_capture_on_commit_callbacks
):
    login(tenant_b.owner.email)
    assert api_client.get(URL).json()["count"] == 0
    assert api_client.get(f"{URL}{pending.id}/").status_code == 404
    response = _post(api_client, django_capture_on_commit_callbacks, f"{URL}{pending.id}/approve/")
    assert response.status_code == 404


def test_conversation_shows_pending_drafts(pending, api_client):
    item = api_client.get("/api/v1/conversations/").json()["results"][0]
    assert item["pending_drafts"] == 1


def test_guardrail_original_text_visible_only_on_blocked_drafts(pending, api_client):
    assert api_client.get(f"{URL}{pending.id}/").json()["original_ai_text"] == ""


# ------------------------------------------------------------------ auditoria append-only


def test_audit_events_cannot_be_updated_or_deleted(tenant_a, pending):
    with tenant_context(tenant_a.tenant.id):
        event = AuditEvent.objects.first()
        assert event is not None
        for sql in (
            "UPDATE core_auditevent SET action = 'x' WHERE id = %s",
            "DELETE FROM core_auditevent WHERE id = %s",
        ):
            with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cur:
                cur.execute(sql, [event.id])
        with pytest.raises(ValueError, match="imutável"):
            event.save()


def test_term_acceptance_is_append_only_in_database(tenant_a, pending):
    with (
        tenant_context(tenant_a.tenant.id),
        pytest.raises(DatabaseError),
        transaction.atomic(),
        connection.cursor() as cur,
    ):
        cur.execute("UPDATE clientes_clienttermacceptance SET evidence = 'x'")


def test_app_role_has_no_update_or_delete_on_append_only_tables():
    with connection.cursor() as cur:
        cur.execute(
            "SELECT has_table_privilege(current_user, 'core_auditevent', 'UPDATE'), "
            "has_table_privilege(current_user, 'core_auditevent', 'DELETE'), "
            "has_table_privilege(current_user, 'core_auditevent', 'INSERT')"
        )
        assert cur.fetchone() == (False, False, True)


def test_manual_reply_is_audited(
    tenant_a,
    account_a,
    inbound,
    login,
    api_client,
    django_capture_on_commit_callbacks,
    fake_gateway,
    fake_llm,
):
    inbound("Oi")
    login(tenant_a.owner.email)
    with tenant_context(tenant_a.tenant.id):
        conversation = Conversation.objects.get()
    _post(
        api_client,
        django_capture_on_commit_callbacks,
        f"/api/v1/conversations/{conversation.id}/messages/",
        {"body": "Oi! Tudo bem?"},
    )
    with tenant_context(tenant_a.tenant.id):
        message = Message.objects.get(direction="OUT", body="Oi! Tudo bem?")
        event = AuditEvent.objects.get(action="message.manual_reply")
    assert event.entity_id == message.id
    assert event.actor_user == tenant_a.owner

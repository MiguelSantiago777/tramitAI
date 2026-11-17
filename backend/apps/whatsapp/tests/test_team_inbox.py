from apps.accounts.models import Membership, User
from apps.core.models import AuditEvent
from apps.core.tenancy import tenant_context
from apps.whatsapp.models import Conversation, QuickReply

CONVERSATIONS = "/api/v1/conversations/"
REPLIES = "/api/v1/quick-replies/"


def _conversation_id(tenant_a):
    with tenant_context(tenant_a.tenant.id):
        return str(Conversation.objects.get().pk)


def test_assign_and_filter_mine_or_unassigned(tenant_a, account_a, inbound, login, api_client):
    inbound("Oi")
    inbound("Olá", wa_id="5521911112222", name="Bruno")
    lawyer = User.objects.create_user(email="adv@a.test", password="senha-de-teste-123")
    Membership.objects.create(user=lawyer, tenant=tenant_a.tenant, role=Membership.Role.LAWYER)
    login(tenant_a.owner.email)
    with tenant_context(tenant_a.tenant.id):
        maria = Conversation.objects.get(wa_id="5521998765432")

    response = api_client.patch(
        f"{CONVERSATIONS}{maria.pk}/", {"assignee_id": str(lawyer.pk)}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["assignee_name"] == "adv@a.test"

    def names(query: str) -> set[str]:
        return {
            c["contact_name"] for c in api_client.get(f"{CONVERSATIONS}?{query}").json()["results"]
        }

    assert names("assignee=none") == {"Bruno"}
    login("adv@a.test")
    assert names("assignee=me") == {"Maria"}
    with tenant_context(tenant_a.tenant.id):
        assert AuditEvent.objects.filter(action="conversation.assigned").count() == 1


def test_cannot_assign_member_of_other_office(
    tenant_a, tenant_b, account_a, inbound, login, api_client
):
    inbound("Oi")
    login(tenant_a.owner.email)
    response = api_client.patch(
        f"{CONVERSATIONS}{_conversation_id(tenant_a)}/",
        {"assignee_id": str(tenant_b.owner.pk)},
        format="json",
    )
    assert response.status_code == 400


def test_quick_replies_crud_and_isolation(tenant_a, tenant_b, login, api_client):
    login(tenant_a.owner.email)
    created = api_client.post(
        REPLIES,
        {"title": "Documentos", "body": "Olá, {nome}! Envie RG, CPF e comprovante de residência."},
        format="json",
    )
    assert created.status_code == 201
    assert [r["title"] for r in api_client.get(REPLIES).json()] == ["Documentos"]
    rid = created.json()["id"]
    assert api_client.patch(f"{REPLIES}{rid}/", {"title": "Docs"}, format="json").status_code == 200

    login(tenant_b.owner.email)
    assert api_client.get(REPLIES).json() == []
    assert api_client.get(f"{REPLIES}{rid}/").status_code == 404

    login(tenant_a.owner.email)
    assert api_client.delete(f"{REPLIES}{rid}/").status_code == 204
    with tenant_context(tenant_a.tenant.id):
        assert QuickReply.objects.count() == 0

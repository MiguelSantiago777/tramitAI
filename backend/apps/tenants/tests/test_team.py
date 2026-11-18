import re

from django.core import mail

from apps.accounts.models import Membership, User
from apps.core.models import AuditEvent
from apps.core.tenancy import tenant_context
from apps.tenants.models import Tenant, TenantSettings

TEAM = "/api/v1/tenant/team/"
SETTINGS = "/api/v1/tenant/settings/"
CONFIRM = "/api/v1/auth/password-reset/confirm/"


def _invite(api_client, callbacks, **body):
    with callbacks(execute=True):
        return api_client.post(TEAM, body, format="json")


def test_owner_invites_new_person_who_sets_password_and_logs_in(
    tenant_a, api_client, login, django_capture_on_commit_callbacks
):
    login(tenant_a.owner.email)
    response = _invite(
        api_client,
        django_capture_on_commit_callbacks,
        email="Nova.Adv@Exemplo.com",
        full_name="Nova Advogada",
        role="LAWYER",
    )
    assert response.status_code == 201
    assert response.json()["pending"] is True

    [email] = mail.outbox
    assert email.to == ["nova.adv@exemplo.com"]
    assert "Escritorio A" in email.subject
    match = re.search(r"uid=([^&\s]+)&token=([^&\s]+)&convite=1", str(email.body))
    assert match

    api_client.credentials()
    ok = api_client.post(
        CONFIRM,
        {"uid": match.group(1), "token": match.group(2), "password": "senha-da-nova-adv-1"},
        format="json",
    )
    assert ok.status_code == 204
    assert login("nova.adv@exemplo.com", password="senha-da-nova-adv-1").status_code == 200


def test_existing_user_from_other_office_is_added_without_new_account(
    tenant_a, tenant_b, api_client, login, django_capture_on_commit_callbacks
):
    login(tenant_a.owner.email)
    _invite(
        api_client, django_capture_on_commit_callbacks, email=tenant_b.owner.email, role="STAFF"
    )
    assert User.objects.filter(email=tenant_b.owner.email).count() == 1
    assert Membership.objects.filter(user=tenant_b.owner, tenant=tenant_a.tenant).exists()


def test_inviting_current_member_is_conflict(
    tenant_a, api_client, login, django_capture_on_commit_callbacks
):
    login(tenant_a.owner.email)
    response = _invite(
        api_client, django_capture_on_commit_callbacks, email=tenant_a.owner.email, role="STAFF"
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "already_member"


def test_only_owner_manages_team(tenant_a, api_client, login, django_capture_on_commit_callbacks):
    lawyer = User.objects.create_user(email="adv@a.test", password="senha-de-teste-123")
    Membership.objects.create(user=lawyer, tenant=tenant_a.tenant, role=Membership.Role.LAWYER)
    login("adv@a.test")
    assert api_client.get(TEAM).status_code == 200
    denied = _invite(api_client, django_capture_on_commit_callbacks, email="x@x.test", role="STAFF")
    assert denied.status_code == 403


def test_change_role_deactivate_and_guards(tenant_a, api_client, login):
    lawyer = User.objects.create_user(email="adv@a.test", password="senha-de-teste-123")
    membership = Membership.objects.create(
        user=lawyer, tenant=tenant_a.tenant, role=Membership.Role.LAWYER
    )
    login(tenant_a.owner.email)

    promoted = api_client.patch(f"{TEAM}{membership.pk}/", {"role": "OWNER"}, format="json")
    assert promoted.json()["role"] == "OWNER"
    off = api_client.patch(f"{TEAM}{membership.pk}/", {"is_active": False}, format="json")
    assert off.json()["is_active"] is False
    assert login("adv@a.test").status_code != 200  # sem vínculo ativo, não entra

    login(tenant_a.owner.email)
    me = tenant_a.membership
    self_change = api_client.patch(f"{TEAM}{me.pk}/", {"role": "STAFF"}, format="json")
    assert self_change.json()["error"]["code"] == "cannot_change_self"
    with tenant_context(tenant_a.tenant.id):
        assert AuditEvent.objects.filter(action="team.updated").count() == 2


def test_service_never_leaves_office_without_owner(tenant_a):
    import pytest

    from apps.accounts.team import update_member
    from apps.core.exceptions import ApiError

    other = User.objects.create_user(email="outro@a.test", password="senha-de-teste-123")
    with pytest.raises(ApiError) as exc:
        update_member(tenant_a.membership, actor=other, role="LAWYER", is_active=None)
    assert exc.value.error_code == "last_owner"


def test_member_of_other_office_is_404(tenant_a, tenant_b, api_client, login):
    login(tenant_a.owner.email)
    other = tenant_b.membership
    assert (
        api_client.patch(f"{TEAM}{other.pk}/", {"role": "STAFF"}, format="json").status_code == 404
    )


def test_owner_edits_office_settings(tenant_a, api_client, login):
    login(tenant_a.owner.email)
    response = api_client.patch(
        SETTINGS,
        {
            "tenant_name": "Silva & Souza Advogados",
            "ai_triage_enabled": False,
            "staff_can_approve": True,
        },
        format="json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["tenant_name"] == "Silva & Souza Advogados"
    assert body["ai_triage_enabled"] is False
    assert Tenant.objects.get(pk=tenant_a.tenant.id).name == "Silva & Souza Advogados"
    with tenant_context(tenant_a.tenant.id):
        assert TenantSettings.objects.get().staff_can_approve is True


def test_owner_turns_on_automatic_triage(tenant_a, api_client, login):
    login(tenant_a.owner.email)
    with tenant_context(tenant_a.tenant.id):
        assert TenantSettings.objects.get().auto_send_simple_replies is False  # começa desligado
    api_client.patch(SETTINGS, {"auto_send_simple_replies": True}, format="json")
    with tenant_context(tenant_a.tenant.id):
        assert TenantSettings.objects.get().auto_send_simple_replies is True


def test_lawyer_cannot_edit_settings(tenant_a, api_client, login):
    lawyer = User.objects.create_user(email="adv@a.test", password="senha-de-teste-123")
    Membership.objects.create(user=lawyer, tenant=tenant_a.tenant, role=Membership.Role.LAWYER)
    login("adv@a.test")
    assert (
        api_client.patch(SETTINGS, {"ai_triage_enabled": False}, format="json").status_code == 403
    )

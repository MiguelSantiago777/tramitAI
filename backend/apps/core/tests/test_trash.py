"""Lixeira: remover cliente/processo, esconder das listas, restaurar e apagar de vez."""

from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.accounts.models import Membership, User
from apps.clientes.models import Client
from apps.core import trash
from apps.core.tenancy import tenant_context
from apps.processos.models import CaseClient, LegalCase
from apps.processos.tests.factories import make_cnj

pytestmark = pytest.mark.django_db

CLIENTS = "/api/v1/clients/"
CASES = "/api/v1/cases/"
TRASH = "/api/v1/trash/"
AGREEMENTS = "/api/v1/fee-agreements/"


@pytest.fixture
def as_a(tenant_a: Any, login: Any) -> Any:
    login(tenant_a.owner.email)
    return tenant_a


@pytest.fixture
def ana(tenant_a: Any) -> Client:
    with tenant_context(tenant_a.tenant.id):
        return Client.objects.create(name="Ana Souza", cpf_cnpj="52998224725")


@pytest.fixture
def case(tenant_a: Any, ana: Client) -> LegalCase:
    with tenant_context(tenant_a.tenant.id):
        c = LegalCase.objects.create(cnj_number=make_cnj())
        CaseClient.objects.create(case=c, client=ana)
        return c


def test_remove_client_hides_everywhere_and_restore_brings_back(as_a, api_client, ana, case):
    assert api_client.delete(f"{CLIENTS}{ana.pk}/").status_code == 204

    assert api_client.get(CLIENTS).json()["count"] == 0
    assert api_client.get(f"{CLIENTS}{ana.pk}/").status_code == 404
    assert api_client.get(f"{CASES}{case.pk}/").json()["clients"] == []

    items = api_client.get(TRASH).json()
    assert [(i["kind"], i["label"]) for i in items] == [("client", "Ana Souza")]
    assert items[0]["deleted_by_name"]

    # Mesmo CPF não pode ser cadastrado de novo: avisa que está na lixeira.
    dup = api_client.post(CLIENTS, {"name": "Ana", "cpf_cnpj": "529.982.247-25"}, format="json")
    assert dup.status_code == 400
    assert "Lixeira" in dup.json()["error"]["details"]["cpf_cnpj"][0]

    assert api_client.post(f"{TRASH}client/{ana.pk}/restore/").status_code == 204
    assert api_client.get(CLIENTS).json()["count"] == 1
    assert len(api_client.get(f"{CASES}{case.pk}/").json()["clients"]) == 1
    assert api_client.get(TRASH).json() == []


def test_open_installments_need_confirmation(as_a, api_client, ana):
    body = {
        "client_id": str(ana.pk),
        "title": "Ação",
        "total_amount": "900.00",
        "installments_count": 3,
        "first_due": "2026-12-10",
    }
    assert api_client.post(AGREEMENTS, body, format="json").status_code == 201
    blocked = api_client.delete(f"{CLIENTS}{ana.pk}/")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "has_open_installments"
    assert api_client.delete(f"{CLIENTS}{ana.pk}/?force=1").status_code == 204
    assert api_client.get(AGREEMENTS).json()["count"] == 0  # some do financeiro também


def test_remove_case_and_cnj_points_to_trash(as_a, api_client, case):
    assert api_client.delete(f"{CASES}{case.pk}/").status_code == 204
    assert api_client.get(CASES).json()["count"] == 0
    again = api_client.post(CASES, {"cnj_number": case.cnj_number}, format="json")
    assert again.status_code == 400
    assert "Lixeira" in again.json()["error"]["details"]["cnj_number"][0]
    assert api_client.post(f"{TRASH}case/{case.pk}/restore/").status_code == 204
    assert api_client.get(CASES).json()["count"] == 1


def test_staff_cannot_remove_and_only_owner_purges(tenant_a, login, api_client, ana):
    staff = User.objects.create_user(email="equipe@a.test", password="senha-de-teste-123")
    Membership.objects.create(user=staff, tenant=tenant_a.tenant, role=Membership.Role.STAFF)
    lawyer = User.objects.create_user(email="adv@a.test", password="senha-de-teste-123")
    Membership.objects.create(user=lawyer, tenant=tenant_a.tenant, role=Membership.Role.LAWYER)

    login("equipe@a.test")
    assert api_client.delete(f"{CLIENTS}{ana.pk}/").status_code == 403

    login("adv@a.test")
    assert api_client.delete(f"{CLIENTS}{ana.pk}/").status_code == 204
    assert api_client.delete(f"{TRASH}client/{ana.pk}/").status_code == 403

    login(tenant_a.owner.email)
    assert api_client.delete(f"{TRASH}client/{ana.pk}/").status_code == 204
    with tenant_context(tenant_a.tenant.id):
        assert not Client.with_deleted.filter(pk=ana.pk).exists()


def test_purge_removes_dependents(as_a, api_client, ana, case):
    body = {
        "client_id": str(ana.pk),
        "title": "Ação",
        "total_amount": "100.00",
        "installments_count": 1,
        "first_due": "2026-12-10",
    }
    api_client.post(AGREEMENTS, body, format="json")
    api_client.delete(f"{CLIENTS}{ana.pk}/?force=1")
    assert api_client.delete(f"{TRASH}client/{ana.pk}/").status_code == 204
    with tenant_context(as_a.tenant.id):
        assert not CaseClient.objects.filter(client_id=ana.pk).exists()
        assert LegalCase.objects.filter(pk=case.pk).exists()  # processo continua


def test_purge_keeps_term_acceptance_but_anonymizes(as_a, api_client, ana):
    accepted = api_client.post(
        f"{CLIENTS}{ana.pk}/term-acceptances/",
        {"accepted_at": "2026-11-01T10:00:00Z", "channel": "IN_PERSON"},
        format="json",
    )
    assert accepted.status_code == 201, accepted.content
    api_client.delete(f"{CLIENTS}{ana.pk}/")
    assert api_client.delete(f"{TRASH}client/{ana.pk}/").status_code == 204
    assert api_client.get(TRASH).json() == []
    with tenant_context(as_a.tenant.id):
        row = Client.with_deleted.get(pk=ana.pk)
        assert row.name == "Cliente removido"
        assert row.cpf_cnpj == ""
        assert row.anonymized_at is not None
        assert row.term_acceptances.count() == 1
    # O CPF fica livre para um cadastro novo.
    again = api_client.post(CLIENTS, {"name": "Ana", "cpf_cnpj": "52998224725"}, format="json")
    assert again.status_code == 201


def test_expired_items_are_purged_daily(tenant_a, ana, case):
    with tenant_context(tenant_a.tenant.id):
        trash.trash_case(case, user=tenant_a.owner)
        trash.trash_client(ana, user=tenant_a.owner)
        old = timezone.now() - timedelta(days=31)
        LegalCase.with_deleted.filter(pk=case.pk).update(deleted_at=old)
    assert trash.purge_expired() == 1  # só o processo venceu
    with tenant_context(tenant_a.tenant.id):
        assert not LegalCase.with_deleted.filter(pk=case.pk).exists()
        assert Client.with_deleted.filter(pk=ana.pk).exists()


def test_trash_is_per_tenant(tenant_a, tenant_b, login, api_client, ana):
    login(tenant_a.owner.email)
    api_client.delete(f"{CLIENTS}{ana.pk}/")
    login(tenant_b.owner.email)
    assert api_client.get(TRASH).json() == []
    assert api_client.post(f"{TRASH}client/{ana.pk}/restore/").status_code == 404
    assert api_client.delete(f"{TRASH}client/{ana.pk}/").status_code == 404

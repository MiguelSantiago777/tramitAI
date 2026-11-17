from apps.accounts.models import Membership, User
from apps.core.tenancy import tenant_context
from apps.tenants.models import ClientTermVersion, Tenant, TenantSettings

ADD = "/admin/tenants/tenant/add/"


def _master(client):
    master = User.objects.create_superuser(email="master@tramitai.test", password="x" * 20)
    client.force_login(master)
    return master


def test_master_creates_complete_office_in_admin(db, client):
    _master(client)
    response = client.post(
        ADD,
        {
            "name": "Silva Advocacia",
            "slug": "",
            "owner_email": "dra.silva@exemplo.com",
            "owner_name": "Ana Silva",
            "owner_password": "senha-forte-do-titular-1",
        },
    )
    assert response.status_code == 302, response.content[:500]

    tenant = Tenant.objects.get(name="Silva Advocacia")
    assert tenant.slug == "silva-advocacia"
    owner = User.objects.get(email="dra.silva@exemplo.com")
    assert owner.check_password("senha-forte-do-titular-1")
    assert Membership.objects.get(user=owner, tenant=tenant).role == Membership.Role.OWNER
    with tenant_context(tenant.id):
        assert TenantSettings.objects.count() == 1
        term = ClientTermVersion.objects.get(is_active=True)
    assert "Silva Advocacia" in term.body


def test_new_owner_requires_strong_password(db, client):
    _master(client)
    response = client.post(
        ADD, {"name": "Escritório X", "owner_email": "novo@exemplo.com", "owner_password": ""}
    )
    assert response.status_code == 200
    assert not Tenant.objects.filter(name="Escritório X").exists()
    weak = client.post(
        ADD, {"name": "Escritório X", "owner_email": "novo@exemplo.com", "owner_password": "123"}
    )
    assert weak.status_code == 200
    assert not Tenant.objects.filter(name="Escritório X").exists()


def test_existing_user_joins_without_password(tenant_a, client):
    _master(client)
    response = client.post(ADD, {"name": "Segundo Escritório", "owner_email": tenant_a.owner.email})
    assert response.status_code == 302
    second = Tenant.objects.get(name="Segundo Escritório")
    assert Membership.objects.filter(user=tenant_a.owner, tenant=second).exists()

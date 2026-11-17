"""Segunda trava: Row Level Security no Postgres.

Estes testes usam SQL cru e o manager `unscoped` de propósito, para provar que o isolamento
vale mesmo quando o filtro da aplicação é contornado.
"""

import pytest
from django.apps import apps
from django.conf import settings
from django.db import DatabaseError, connection, transaction

from apps.core.db import POLICY_NAME
from apps.core.models import TenantModel
from apps.core.tenancy import TenantContextMissing, TenantMismatch, tenant_context
from apps.tenants.models import TenantSettings

pytestmark = pytest.mark.django_db


def _raw_tenant_ids() -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT tenant_id::text FROM tenants_tenantsettings")
        return {row[0] for row in cursor.fetchall()}


def test_tests_run_as_unprivileged_role():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
        )
        user, is_super, bypass_rls = cursor.fetchone()
    assert user == settings.DB_APP_ROLE
    assert not is_super, "testes rodando como superusuário: o RLS seria ignorado"
    assert not bypass_rls, "role com BYPASSRLS: o RLS seria ignorado"


def test_every_tenant_model_has_forced_rls_and_policy():
    tenant_models = [
        m for m in apps.get_models() if issubclass(m, TenantModel) and not m._meta.abstract
    ]
    assert tenant_models, "nenhum TenantModel encontrado"

    with connection.cursor() as cursor:
        for model in tenant_models:
            table = model._meta.db_table
            cursor.execute(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = %s",
                [table],
            )
            enabled, forced = cursor.fetchone()
            cursor.execute(
                "SELECT count(*) FROM pg_policies WHERE tablename = %s AND policyname = %s",
                [table, POLICY_NAME],
            )
            (policies,) = cursor.fetchone()
            assert enabled, f"{table} sem RLS (falta EnableRLS na migration)"
            assert forced, f"{table} sem FORCE ROW LEVEL SECURITY"
            assert policies == 1, f"{table} sem policy {POLICY_NAME}"


def test_manager_without_tenant_fails_closed(tenant_a, tenant_b):
    with pytest.raises(TenantContextMissing):
        list(TenantSettings.objects.all())


def test_raw_sql_without_tenant_sees_nothing(tenant_a, tenant_b):
    assert _raw_tenant_ids() == set()


def test_empty_tenant_setting_is_fail_closed(tenant_a):
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', '', true)")
    assert _raw_tenant_ids() == set()


def test_manager_sees_only_active_tenant(tenant_a, tenant_b):
    with tenant_context(tenant_a.tenant.id):
        assert {s.tenant_id for s in TenantSettings.objects.all()} == {tenant_a.tenant.id}
    with tenant_context(tenant_b.tenant.id):
        assert {s.tenant_id for s in TenantSettings.objects.all()} == {tenant_b.tenant.id}


def test_rls_holds_when_app_filter_is_bypassed(tenant_a, tenant_b):
    with tenant_context(tenant_a.tenant.id):
        assert {s.tenant_id for s in TenantSettings.unscoped.all()} == {tenant_a.tenant.id}
        assert _raw_tenant_ids() == {str(tenant_a.tenant.id)}


def test_rls_blocks_update_and_delete_of_other_tenant(tenant_a, tenant_b):
    with tenant_context(tenant_a.tenant.id), connection.cursor() as cursor:
        cursor.execute(
            "UPDATE tenants_tenantsettings SET staff_can_approve = true WHERE tenant_id = %s",
            [tenant_b.tenant.id],
        )
        assert cursor.rowcount == 0
        cursor.execute(
            "DELETE FROM tenants_tenantsettings WHERE tenant_id = %s", [tenant_b.tenant.id]
        )
        assert cursor.rowcount == 0


def test_rls_blocks_insert_for_other_tenant(tenant_a, tenant_b):
    with (
        tenant_context(tenant_a.tenant.id),
        pytest.raises(DatabaseError, match="row-level security"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "INSERT INTO tenants_tenantsettings "
            "(id, tenant_id, created_at, updated_at, auto_send_simple_replies, "
            " staff_can_approve, timezone) "
            "VALUES (gen_random_uuid(), %s, now(), now(), false, false, 'UTC')",
            [tenant_b.tenant.id],
        )


def test_save_with_other_tenant_is_rejected_by_app(tenant_a, tenant_b):
    with tenant_context(tenant_a.tenant.id):
        foreign = TenantSettings(tenant_id=tenant_b.tenant.id)
        with pytest.raises(TenantMismatch):
            foreign.save()


def test_tenant_context_restores_previous_tenant(tenant_a, tenant_b):
    with tenant_context(tenant_a.tenant.id):
        with tenant_context(tenant_b.tenant.id):
            assert _raw_tenant_ids() == {str(tenant_b.tenant.id)}
        assert _raw_tenant_ids() == {str(tenant_a.tenant.id)}
    assert _raw_tenant_ids() == set()

"""Operação de migration que liga Row Level Security numa tabela de tenant.

Uso numa migration, logo depois do CreateModel:

    from apps.core.db import EnableRLS
    operations = [migrations.CreateModel(...), EnableRLS("client")]

FORCE faz o RLS valer até para o dono da tabela (tramitai_owner). A policy é fail-closed:
sem `app.tenant_id` na sessão (NULL ou ''), a comparação dá NULL e nenhuma linha passa.
"""

from typing import Any

from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.operations.base import Operation
from django.db.migrations.state import ProjectState

POLICY_NAME = "tenant_isolation"
TENANT_PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


class EnableRLS(Operation):
    reversible = True
    reduces_to_sql = True

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    def state_forwards(self, app_label: str, state: ProjectState) -> None:
        pass

    def _table(self, app_label: str, state: ProjectState, schema_editor: Any) -> str:
        model = state.apps.get_model(app_label, self.model_name)
        return str(schema_editor.quote_name(model._meta.db_table))

    def database_forwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        table = self._table(app_label, to_state, schema_editor)
        schema_editor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        schema_editor.execute(
            f"CREATE POLICY {POLICY_NAME} ON {table} "
            f"USING ({TENANT_PREDICATE}) WITH CHECK ({TENANT_PREDICATE})"
        )

    def database_backwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        table = self._table(app_label, from_state, schema_editor)
        schema_editor.execute(f"DROP POLICY IF EXISTS {POLICY_NAME} ON {table}")
        schema_editor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    def describe(self) -> str:
        return f"Liga RLS por tenant em {self.model_name}"

    def deconstruct(self) -> tuple[str, list[Any], dict[str, Any]]:
        return (self.__class__.__name__, [self.model_name], {})

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


APPEND_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION tramitai_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Tabela % é append-only: % não permitido.', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;
"""


class MakeAppendOnly(Operation):
    """Trigger que bloqueia UPDATE e DELETE na tabela, para qualquer role (inclusive o dono)."""

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
        # params=None: o corpo plpgsql tem '%' e não pode passar pela interpolação do driver.
        schema_editor.execute(APPEND_ONLY_FUNCTION, params=None)
        schema_editor.execute(
            f"CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION tramitai_append_only()"
        )

    def database_backwards(
        self,
        app_label: str,
        schema_editor: BaseDatabaseSchemaEditor,
        from_state: ProjectState,
        to_state: ProjectState,
    ) -> None:
        table = self._table(app_label, from_state, schema_editor)
        schema_editor.execute(f"DROP TRIGGER IF EXISTS append_only ON {table}")

    def describe(self) -> str:
        return f"Torna {self.model_name} append-only"

    def deconstruct(self) -> tuple[str, list[Any], dict[str, Any]]:
        return (self.__class__.__name__, [self.model_name], {})

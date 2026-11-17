from typing import Any

from django.apps import AppConfig
from django.conf import settings
from django.db import connections
from django.db.models.signals import post_migrate


def grant_app_role(using: str = "default", **kwargs: Any) -> None:
    """Dá ao role da aplicação só DML nas tabelas, depois de cada migrate.

    O migrate roda como tramitai_owner (dono das tabelas). O role da aplicação não é dono,
    então não consegue alterar schema, desligar RLS nem fazer TRUNCATE.
    """
    connection = connections[using]
    role = connection.ops.quote_name(settings.DB_APP_ROLE)
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_user")
        row = cursor.fetchone()
        if row and row[0] == settings.DB_APP_ROLE:
            return
        cursor.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}"
        )
        cursor.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}")
        # Tabelas append-only: a aplicação só lê e insere.
        cursor.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = ANY(%s)",
            [list(settings.APPEND_ONLY_TABLES)],
        )
        for (table,) in cursor.fetchall():
            cursor.execute(
                f"REVOKE UPDATE, DELETE ON {connection.ops.quote_name(table)} FROM {role}"
            )


class CoreConfig(AppConfig):
    name = "apps.core"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        post_migrate.connect(grant_app_role, sender=self, dispatch_uid="core.grant_app_role")

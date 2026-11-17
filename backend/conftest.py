"""Fixtures globais.

O banco de teste é criado e migrado como tramitai_owner (DATABASE_OWNER_URL) e, depois disso,
a conexão passa a usar tramitai_app (DATABASE_URL). É o mesmo arranjo de produção: assim o RLS
vale de verdade nos testes. Se rodasse como superusuário, o teste de isolamento passaria por
mentira; `test_tests_run_as_unprivileged_role` trava isso.

Não use `transactional_db`/TransactionTestCase: o flush faz TRUNCATE, que o role da aplicação
não tem (de propósito: TRUNCATE ignora RLS).
"""

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from django.conf import settings
from django.db import connections
from django.test.utils import setup_databases, teardown_databases
from rest_framework.test import APIClient

from apps.tenants.services import CreatedTenant, create_tenant

pytest_plugins = [
    "apps.whatsapp.tests.fixtures",
    "apps.ia.tests.fixtures",
    "apps.processos.tests.fixtures",
]

PASSWORD = "senha-de-teste-123"


def _use_credentials(user: str, password: str) -> None:
    conn = connections["default"]
    conn.close()
    conn.settings_dict["USER"] = user
    conn.settings_dict["PASSWORD"] = password


@pytest.fixture(scope="session")
def django_db_setup(django_test_environment: None, django_db_blocker: Any) -> Iterator[None]:
    conn = connections["default"]
    app_user, app_password = conn.settings_dict["USER"], conn.settings_dict["PASSWORD"]
    owner = settings.DATABASE_OWNER

    _use_credentials(owner["USER"], owner["PASSWORD"])
    with django_db_blocker.unblock():
        db_config = setup_databases(verbosity=0, interactive=False, keepdb=False)
    _use_credentials(app_user, app_password)

    yield

    with django_db_blocker.unblock():
        _use_credentials(owner["USER"], owner["PASSWORD"])
        teardown_databases(db_config, verbosity=0)


@pytest.fixture
def make_tenant(db: None) -> Callable[..., CreatedTenant]:
    def _make(name: str, owner_email: str | None = None) -> CreatedTenant:
        slug = name.lower().replace(" ", "-")
        return create_tenant(
            name=name,
            owner_email=owner_email or f"titular@{slug}.test",
            owner_password=PASSWORD,
        )

    return _make


@pytest.fixture
def tenant_a(make_tenant: Callable[..., CreatedTenant]) -> CreatedTenant:
    return make_tenant("Escritorio A")


@pytest.fixture
def tenant_b(make_tenant: Callable[..., CreatedTenant]) -> CreatedTenant:
    return make_tenant("Escritorio B")


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def login(api_client: APIClient) -> Callable[..., Any]:
    """Faz login e já deixa o client autenticado. Devolve a resposta."""

    def _login(email: str, tenant_id: Any = None, password: str = PASSWORD) -> Any:
        body: dict[str, Any] = {"email": email, "password": password}
        if tenant_id is not None:
            body["tenant_id"] = str(tenant_id)
        response = api_client.post("/api/v1/auth/login/", body, format="json")
        if response.status_code == 200:
            api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.json()['access']}")
        return response

    return _login

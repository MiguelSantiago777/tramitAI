from typing import Any

from django.db import models


def schema_safe_queryset(view: Any, model: type[models.Model]) -> models.QuerySet[Any] | None:
    """Queryset vazio para o drf-spectacular gerar o schema sem tenant ativo.

    Retorna None em requests normais (aí a view monta o queryset de verdade).
    """
    if getattr(view, "swagger_fake_view", False):
        return model.unscoped.none()  # type: ignore[attr-defined]
    return None


class OutsideTransactionMixin:
    """Para views que chamam serviço externo (HTTP) e por isso rodam fora do ATOMIC_REQUESTS.

    Registre a URL com `transaction.non_atomic_requests(...)`. A autenticação roda numa
    transação curta; o banco é usado com `tenant_atomic` nos trechos que precisam.
    """

    def perform_authentication(self, request: Any) -> None:
        from django.db import transaction

        from apps.core.tenancy import clear_tenant

        with transaction.atomic():
            request.user  # noqa: B018 - dispara a autenticação
        clear_tenant()

    def handle_exception(self, exc: Exception) -> Any:
        from django.db import connection

        # Sem transação própria: não deixa o handler do DRF marcar rollback numa transação
        # externa que não existe.
        needs_rollback = connection.needs_rollback
        response = super().handle_exception(exc)  # type: ignore[misc]
        connection.needs_rollback = needs_rollback
        return response

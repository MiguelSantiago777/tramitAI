import uuid
from typing import Any

from django.db import models

from .tenancy import TenantMismatch, get_current_tenant_id


class TenantManager[M: models.Model](models.Manager[M]):
    """Manager padrão de dados de tenant: sempre filtra pelo tenant ativo.

    Sem tenant ativo, levanta TenantContextMissing em vez de devolver tudo.
    """

    def get_queryset(self) -> models.QuerySet[M]:
        return super().get_queryset().filter(tenant_id=get_current_tenant_id())


class TenantModel(models.Model):
    """Base de toda tabela de negócio (data plane).

    Toda subclasse concreta precisa de uma migration com `EnableRLS` (apps.core.db).
    Há um teste que falha se alguma tabela de TenantModel estiver sem RLS.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.PROTECT, related_name="+", editable=False
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects: TenantManager[Any] = TenantManager()
    # Sem o filtro da aplicação, mas o RLS continua valendo. Uso restrito (ex.: testes de RLS).
    unscoped: models.Manager[Any] = models.Manager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        current = get_current_tenant_id()
        if self.tenant_id is None:
            self.tenant_id = current
        elif self.tenant_id != current:
            raise TenantMismatch("Registro pertence a outro tenant.")
        super().save(*args, **kwargs)

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


class ActiveTenantManager[M: models.Model](TenantManager[M]):
    """Manager padrão de quem tem lixeira: esconde o que foi removido (deleted_at preenchido)."""

    def get_queryset(self) -> models.QuerySet[M]:
        return super().get_queryset().filter(deleted_at__isnull=True)


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


class AuditEvent(TenantModel):
    """Trilha de auditoria append-only (trigger no banco + sem UPDATE/DELETE para a aplicação).

    Guarda quem fez o quê e quando, com referências por id. Conteúdo de mensagem NÃO entra em
    `data`: ele fica nas tabelas de origem (que podem ser anonimizadas por LGPD).
    """

    class ActorType(models.TextChoices):
        USER = "USER", "Usuário"
        SYSTEM = "SYSTEM", "Sistema"
        AI = "AI", "IA"

    actor_type = models.CharField(max_length=8, choices=ActorType.choices)
    actor_user = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    action = models.CharField(max_length=64)
    entity_type = models.CharField(max_length=64)
    entity_id = models.UUIDField()
    data = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "evento de auditoria"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["tenant", "entity_type", "entity_id"], name="audit_entity_idx"),
            models.Index(fields=["tenant", "-created_at"], name="audit_recent_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.action} {self.entity_type}:{self.entity_id}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValueError("Evento de auditoria é imutável.")
        super().save(*args, **kwargs)


class SoftDeletable(models.Model):
    """Lixeira: removido some das listas (manager `objects`), restaurável por 30 dias.

    Use com `objects = ActiveTenantManager()` e `with_deleted = TenantManager()` na classe
    concreta e `default_manager_name = "objects"` no Meta. Regras em apps.core.trash.
    """

    deleted_at = models.DateTimeField(null=True, blank=True, editable=False, db_index=True)
    deleted_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        editable=False,
    )

    class Meta:
        abstract = True

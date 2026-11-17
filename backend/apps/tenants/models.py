import uuid

from django.db import models

from apps.core.models import TenantModel


class Tenant(models.Model):
    """Escritório. Control plane: sem RLS, lido antes de existir tenant ativo."""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Ativo"
        SUSPENDED = "SUSPENDED", "Suspenso"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField("nome", max_length=200)
    slug = models.SlugField(max_length=60, unique=True)
    cnpj = models.CharField(max_length=14, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "escritório"
        verbose_name_plural = "escritórios"

    def __str__(self) -> str:
        return self.name


class TenantSettings(TenantModel):
    """Configurações do escritório (data plane, com RLS)."""

    # A IA nunca envia sozinha. Esta flag existe para o futuro e fica desligada por padrão.
    auto_send_simple_replies = models.BooleanField(default=False)
    # Aprovação de rascunhos: OWNER e LAWYER sempre; STAFF só se ligado aqui.
    staff_can_approve = models.BooleanField(default=False)
    # Retenção (LGPD). Null = sem expurgo automático. Só a estrutura por enquanto.
    data_retention_days = models.PositiveIntegerField(null=True, blank=True)
    message_retention_days = models.PositiveIntegerField(null=True, blank=True)
    timezone = models.CharField(max_length=64, default="America/Sao_Paulo")

    class Meta:
        verbose_name = "configuração do escritório"
        constraints = [
            models.UniqueConstraint(fields=["tenant"], name="tenant_settings_one_per_tenant"),
        ]

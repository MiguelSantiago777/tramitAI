import uuid

from django.conf import settings
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


def default_business_hours() -> dict[str, list[list[str]]]:
    """Segunda a sexta, 9h-12h e 13h-18h. Chave = dia da semana (0 = segunda)."""
    return {str(d): [["09:00", "12:00"], ["13:00", "18:00"]] if d < 5 else [] for d in range(7)}


class TenantSettings(TenantModel):
    """Configurações do escritório (data plane, com RLS)."""

    # Triagem automática: a Lia conversa sozinha com contato novo (desligada por padrão).
    auto_send_simple_replies = models.BooleanField(default=False)
    # Horário de atendimento (a Lia avisa fora dele) e agenda de consultas da Lia.
    business_hours = models.JSONField(default=default_business_hours)
    scheduling_enabled = models.BooleanField("Lia oferece horários", default=False)
    consult_minutes = models.PositiveSmallIntegerField("duração da consulta", default=60)
    scheduling_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="agenda de quem",
    )
    # Aprovação de rascunhos: OWNER e LAWYER sempre; STAFF só se ligado aqui.
    staff_can_approve = models.BooleanField(default=False)
    # Desliga a triagem por IA do escritório (mensagens continuam chegando no inbox).
    ai_triage_enabled = models.BooleanField(default=True)
    # Retenção (LGPD). Null = sem expurgo automático. Só a estrutura por enquanto.
    data_retention_days = models.PositiveIntegerField(null=True, blank=True)
    message_retention_days = models.PositiveIntegerField(null=True, blank=True)
    timezone = models.CharField(max_length=64, default="America/Sao_Paulo")

    class Meta:
        verbose_name = "configuração do escritório"
        constraints = [
            models.UniqueConstraint(fields=["tenant"], name="tenant_settings_one_per_tenant"),
        ]


class ClientTermVersion(TenantModel):
    """Termo de ciência de uso de IA para o cliente final do escritório.

    Editar = publicar nova versão. Versões antigas nunca mudam, porque os aceites apontam
    para a versão exata que o cliente viu.
    """

    version = models.PositiveIntegerField()
    body = models.TextField("texto")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = "versão do termo de ciência"
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "version"], name="term_version_unique"),
            models.UniqueConstraint(
                fields=["tenant"],
                condition=models.Q(is_active=True),
                name="term_one_active_per_tenant",
            ),
        ]

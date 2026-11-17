from typing import Any

from django.conf import settings
from django.db import models

from apps.core.models import TenantModel

from .cnj import format_cnj, tribunal_alias


class LegalCase(TenantModel):
    """Processo judicial acompanhado pelo escritório."""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Ativo"
        ARCHIVED = "ARCHIVED", "Arquivado"

    # 20 dígitos, sem pontuação. Formatação só na saída.
    cnj_number = models.CharField("número CNJ", max_length=20)
    # Derivado do número (J + TR), no padrão de alias do DataJud. Vazio se desconhecido.
    tribunal_alias = models.CharField(max_length=20, blank=True, default="", editable=False)
    classe = models.CharField(max_length=255, blank=True, default="")
    assunto = models.CharField(max_length=255, blank=True, default="")
    orgao_julgador = models.CharField("órgão julgador", max_length=255, blank=True, default="")
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="responsável",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    monitoring_enabled = models.BooleanField("monitorar andamento", default=True)
    last_checked_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_movement_at = models.DateTimeField(null=True, blank=True, editable=False)
    notes = models.TextField("observações", blank=True, default="")

    clients: models.ManyToManyField[Any, Any] = models.ManyToManyField(
        "clientes.Client", through="CaseClient", related_name="cases"
    )

    class Meta:
        verbose_name = "processo"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "cnj_number"], name="case_cnj_unique"),
        ]

    def __str__(self) -> str:
        return self.cnj_formatted

    @property
    def cnj_formatted(self) -> str:
        return format_cnj(self.cnj_number)

    @property
    def tribunal_label(self) -> str:
        return self.tribunal_alias.upper()

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.tribunal_alias = tribunal_alias(self.cnj_number) or ""
        super().save(*args, **kwargs)


class CaseClient(TenantModel):
    """Vínculo processo ↔ cliente, com o papel do cliente no processo."""

    class Role(models.TextChoices):
        AUTHOR = "AUTHOR", "Autor"
        DEFENDANT = "DEFENDANT", "Réu"
        OTHER = "OTHER", "Outro"

    case = models.ForeignKey(LegalCase, on_delete=models.CASCADE, related_name="case_clients")
    client = models.ForeignKey(
        "clientes.Client", on_delete=models.PROTECT, related_name="case_links"
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.AUTHOR)

    class Meta:
        verbose_name = "cliente do processo"
        constraints = [
            models.UniqueConstraint(fields=["case", "client"], name="case_client_unique"),
        ]

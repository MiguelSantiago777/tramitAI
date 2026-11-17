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

    class SyncStatus(models.TextChoices):
        NEVER = "NEVER", "Nunca consultado"
        OK = "OK", "Atualizado"
        NOT_FOUND = "NOT_FOUND", "Não encontrado na fonte"
        ERROR = "ERROR", "Erro na consulta"

    monitoring_enabled = models.BooleanField("monitorar andamento", default=True)
    last_checked_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_movement_at = models.DateTimeField(null=True, blank=True, editable=False)
    sync_status = models.CharField(
        max_length=10, choices=SyncStatus.choices, default=SyncStatus.NEVER, editable=False
    )
    # Só código técnico do erro (ex.: http_429), nunca conteúdo.
    sync_error = models.CharField(max_length=64, blank=True, default="", editable=False)
    # Primeira consulta bem-sucedida: o histórico encontrado ali vira base, sem aviso ao cliente.
    baseline_at = models.DateTimeField(null=True, blank=True, editable=False)
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


class CaseMovement(TenantModel):
    """Andamento do processo vindo da fonte (DataJud). Dados públicos do tribunal.

    A fonte não dá id para movimento: `fingerprint` é um hash do conteúdo e deduplica.
    """

    class Notification(models.TextChoices):
        # Já existia na primeira consulta (ou é antigo demais): não vira aviso.
        BASELINE = "BASELINE", "Histórico"
        PENDING = "PENDING", "Aguardando aviso"
        NOTIFIED = "NOTIFIED", "Cliente avisado"
        SKIPPED = "SKIPPED", "Sem aviso"

    case = models.ForeignKey(LegalCase, on_delete=models.CASCADE, related_name="movements")
    source = models.CharField(max_length=16)
    fingerprint = models.CharField(max_length=64)
    code = models.PositiveIntegerField(null=True, blank=True)
    name = models.CharField(max_length=255)
    complements = models.JSONField(default=list, blank=True)
    grau = models.CharField(max_length=8, blank=True, default="")
    occurred_at = models.DateTimeField()
    notification = models.CharField(
        max_length=10, choices=Notification.choices, default=Notification.PENDING
    )

    class Meta:
        verbose_name = "andamento"
        ordering = ["-occurred_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["case", "fingerprint"], name="case_movement_fingerprint_unique"
            ),
        ]
        indexes = [
            models.Index(fields=["case", "-occurred_at"], name="case_movement_recent_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name} em {self.occurred_at:%d/%m/%Y}"

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


# fmt: off
UFS = [
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA",
    "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
]
# fmt: on


class MonitoredOab(TenantModel):
    """OAB cujas publicações no Diário (DJEN) o escritório acompanha."""

    number = models.CharField("número OAB", max_length=10)
    uf = models.CharField("UF", max_length=2, choices=[(u, u) for u in UFS])
    lawyer_name = models.CharField("advogado(a)", max_length=200, blank=True, default="")
    # Quem recebe as tarefas das publicações sem processo cadastrado.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="usuário",
    )
    is_active = models.BooleanField("monitorar", default=True)
    last_checked_at = models.DateTimeField(null=True, blank=True, editable=False)
    # Até que dia (inclusive) já buscamos com sucesso. A próxima busca recomeça 1 dia antes.
    fetched_until = models.DateField(null=True, blank=True, editable=False)
    last_error = models.CharField(max_length=64, blank=True, default="", editable=False)

    class Meta:
        verbose_name = "OAB monitorada"
        ordering = ["uf", "number"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "number", "uf"], name="monitored_oab_unique"),
        ]

    def __str__(self) -> str:
        return f"OAB {self.number}/{self.uf}"


class Publication(TenantModel):
    """Comunicação publicada no Diário de Justiça Eletrônico Nacional (intimação, citação...).

    Texto já convertido para texto puro (nunca HTML). Dado público do tribunal.
    """

    class Status(models.TextChoices):
        NEW = "NEW", "Nova"
        DONE = "DONE", "Tratada"
        IGNORED = "IGNORED", "Ignorada"

    djen_id = models.BigIntegerField()
    oab = models.ForeignKey(
        MonitoredOab, on_delete=models.SET_NULL, null=True, blank=True, related_name="publications"
    )
    legal_case = models.ForeignKey(
        LegalCase,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="publications",
    )
    cnj_number = models.CharField(max_length=20, blank=True, default="")
    tribunal = models.CharField(max_length=20, blank=True, default="")
    kind = models.CharField("tipo", max_length=60, blank=True, default="")
    document_type = models.CharField(max_length=120, blank=True, default="")
    orgao = models.CharField("órgão", max_length=255, blank=True, default="")
    classe = models.CharField(max_length=255, blank=True, default="")
    available_on = models.DateField("disponibilizada em")
    text = models.TextField(blank=True, default="")
    link = models.URLField(max_length=1000, blank=True, default="")
    recipients = models.JSONField(default=list, blank=True)
    deadline_hints = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEW)
    handled_at = models.DateTimeField(null=True, blank=True)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = "publicação"
        verbose_name_plural = "publicações"
        ordering = ["-available_on", "-djen_id"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "djen_id"], name="publication_djen_unique"),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "status", "-available_on"], name="publication_status_idx"
            ),
            models.Index(fields=["tenant", "cnj_number"], name="publication_cnj_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.kind or 'Publicação'} em {self.available_on:%d/%m/%Y}"

    @property
    def cnj_formatted(self) -> str:
        return format_cnj(self.cnj_number) if self.cnj_number else ""

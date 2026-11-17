"""Funil de novos clientes: do primeiro contato até contratar (ou não)."""

from django.conf import settings
from django.db import models

from apps.core.models import TenantModel


class Opportunity(TenantModel):
    class Stage(models.TextChoices):
        NEW = "NEW", "Novo contato"
        TRIAGE = "TRIAGE", "Em triagem"
        CONSULT = "CONSULT", "Consulta marcada"
        PROPOSAL = "PROPOSAL", "Proposta enviada"
        WON = "WON", "Contratou"
        LOST = "LOST", "Não contratou"

    class Area(models.TextChoices):
        TRABALHISTA = "TRABALHISTA", "Trabalhista"
        PREVIDENCIARIO = "PREVIDENCIARIO", "Previdenciário"
        FAMILIA = "FAMILIA", "Família"
        CONSUMIDOR = "CONSUMIDOR", "Consumidor"
        CIVEL = "CIVEL", "Cível"
        CRIMINAL = "CRIMINAL", "Criminal"
        IMOBILIARIO = "IMOBILIARIO", "Imobiliário"
        TRIBUTARIO = "TRIBUTARIO", "Tributário"
        OUTRA = "OUTRA", "Outra"

    class Source(models.TextChoices):
        WHATSAPP = "WHATSAPP", "WhatsApp"
        INDICACAO = "INDICACAO", "Indicação"
        REDES = "REDES", "Redes sociais"
        SITE = "SITE", "Site / Google"
        PRESENCIAL = "PRESENCIAL", "Presencial"
        OUTRA = "OUTRA", "Outra"

    OPEN_STAGES = (Stage.NEW, Stage.TRIAGE, Stage.CONSULT, Stage.PROPOSAL)

    title = models.CharField("assunto", max_length=200)
    client = models.ForeignKey(
        "clientes.Client", on_delete=models.PROTECT, related_name="opportunities"
    )
    stage = models.CharField(max_length=10, choices=Stage.choices, default=Stage.NEW)
    area = models.CharField(max_length=16, choices=Area.choices, blank=True, default="")
    source = models.CharField(max_length=12, choices=Source.choices, default=Source.WHATSAPP)
    # Honorários estimados (R$). Só informativo para o funil.
    estimated_value = models.DecimalField(
        "valor estimado", max_digits=12, decimal_places=2, null=True, blank=True
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="responsável",
    )
    conversation = models.ForeignKey(
        "whatsapp.Conversation", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    notes = models.TextField("observações", blank=True, default="")
    lost_reason = models.CharField("motivo", max_length=255, blank=True, default="")
    # Ordem dentro da coluna do quadro.
    position = models.PositiveIntegerField(default=0)
    stage_changed_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = "oportunidade"
        verbose_name_plural = "oportunidades"
        ordering = ["stage", "position", "-created_at"]
        indexes = [
            models.Index(fields=["tenant", "stage", "position"], name="opportunity_board_idx"),
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def is_open(self) -> bool:
        return self.stage in self.OPEN_STAGES

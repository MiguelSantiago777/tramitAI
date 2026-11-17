from django.conf import settings
from django.db import models

from apps.core.models import TenantModel


class OutboundDraft(TenantModel):
    """Mensagem que só sai para o cliente depois de aprovada por uma pessoa do escritório.

    Ciclo: DRAFT → APPROVED → SENT, ou DRAFT → REJECTED. APPROVED → FAILED se o WhatsApp
    recusar. Aviso de andamento com a janela de 24h fechada: DRAFT → AWAITING (sai o modelo
    aprovado pela Meta) → APPROVED quando o cliente responde (sai o texto aprovado) → SENT.
    Transições só pelos services; cada uma gera evento de auditoria.
    """

    class Origin(models.TextChoices):
        AI_REPLY = "AI_REPLY", "Resposta da IA"
        TERM_REQUEST = "TERM_REQUEST", "Termo de ciência"
        MOVEMENT_UPDATE = "MOVEMENT_UPDATE", "Atualização de processo"
        EVENT_REMINDER = "EVENT_REMINDER", "Lembrete de compromisso"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Rascunho"
        APPROVED = "APPROVED", "Aprovada"
        AWAITING = "AWAITING", "Aguardando resposta do cliente"
        SENT = "SENT", "Enviada"
        REJECTED = "REJECTED", "Rejeitada"
        FAILED = "FAILED", "Falhou"

    conversation = models.ForeignKey(
        "whatsapp.Conversation", on_delete=models.PROTECT, related_name="drafts"
    )
    client = models.ForeignKey(
        "clientes.Client", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    origin = models.CharField(max_length=16, choices=Origin.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)

    # Texto proposto (IA ou modelo). Nunca é alterado; a edição vai para final_body.
    generated_body = models.TextField()
    final_body = models.TextField(blank=True, default="")

    generation = models.ForeignKey(
        "ia.AiGeneration", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    term_version = models.ForeignKey(
        "tenants.ClientTermVersion",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    source_message = models.ForeignKey(
        "whatsapp.Message", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # Aviso de andamento: processo e andamentos (ids de CaseMovement) que o texto cobre.
    legal_case = models.ForeignKey(
        "processos.LegalCase", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    movement_ids = models.JSONField(default=list, blank=True)
    # Modelo da Meta enviado quando a janela estava fechada (antes do texto).
    template_message = models.OneToOneField(
        "whatsapp.Message",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="template_draft",
    )
    sent_message = models.OneToOneField(
        "whatsapp.Message",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="draft",
    )

    # Triagem (só para o escritório; não vai ao cliente).
    intent = models.CharField(max_length=20, blank=True, default="")
    urgency = models.CharField(max_length=10, blank=True, default="")
    needs_lawyer = models.BooleanField(default=False)
    # Aviso de andamento: a IA acha que interessa ao cliente? (só sugestão para o advogado)
    client_relevant = models.BooleanField(null=True, blank=True)
    summary = models.TextField(blank=True, default="")
    guardrail_flags = models.JSONField(default=list, blank=True)

    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=255, blank=True, default="")
    failure_detail = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        verbose_name = "rascunho de mensagem"
        indexes = [
            models.Index(fields=["tenant", "status", "-created_at"], name="draft_queue_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.origin} {self.status}"

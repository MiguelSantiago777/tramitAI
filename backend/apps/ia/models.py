from django.db import models

from apps.core.models import TenantModel


class AiGeneration(TenantModel):
    """Registro de TODA chamada à IA: prompt (nome/versão), modelo, saída e custo em tokens.

    O texto gerado fica aqui mesmo quando é bloqueado pelos guardrails, para o advogado e a
    auditoria verem o que a IA tentou dizer.
    """

    class Kind(models.TextChoices):
        TRIAGE = "TRIAGE", "Triagem"

    class Status(models.TextChoices):
        OK = "OK", "Gerado"
        ERROR = "ERROR", "Erro"
        REFUSED = "REFUSED", "Recusado pelo modelo"

    kind = models.CharField(max_length=16, choices=Kind.choices)
    status = models.CharField(max_length=8, choices=Status.choices)
    prompt_name = models.CharField(max_length=64)
    prompt_version = models.CharField(max_length=16)
    provider = models.CharField(max_length=32)
    model = models.CharField(max_length=64, blank=True, default="")
    conversation = models.ForeignKey(
        "whatsapp.Conversation", on_delete=models.CASCADE, related_name="+", null=True
    )
    trigger_message = models.ForeignKey(
        "whatsapp.Message", on_delete=models.SET_NULL, related_name="+", null=True
    )
    output_text = models.TextField(blank=True, default="")
    output_data = models.JSONField(null=True, blank=True)
    guardrail_flags = models.JSONField(default=list, blank=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=64, blank=True, default="")
    request_id = models.CharField(max_length=128, blank=True, default="")

    class Meta:
        verbose_name = "geração de IA"
        indexes = [models.Index(fields=["tenant", "-created_at"], name="ai_generation_recent_idx")]

    def __str__(self) -> str:
        return f"{self.kind} {self.status} {self.prompt_name}@{self.prompt_version}"

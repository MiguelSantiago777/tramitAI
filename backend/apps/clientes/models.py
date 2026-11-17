from typing import Any

from django.conf import settings
from django.db import models

from apps.core.models import TenantModel


class Client(TenantModel):
    """Cliente do escritório (ou lead vindo do WhatsApp). Dados pessoais mínimos (LGPD)."""

    class Kind(models.TextChoices):
        PERSON = "PF", "Pessoa física"
        COMPANY = "PJ", "Pessoa jurídica"

    class Status(models.TextChoices):
        LEAD = "LEAD", "Lead"
        ACTIVE = "ACTIVE", "Ativo"
        ARCHIVED = "ARCHIVED", "Arquivado"

    kind = models.CharField(max_length=2, choices=Kind.choices, default=Kind.PERSON)
    name = models.CharField("nome", max_length=200)
    # Só dígitos (CPF) ou A-Z0-9 (CNPJ alfanumérico). Vazio = não informado.
    cpf_cnpj = models.CharField("CPF/CNPJ", max_length=14, blank=True, default="")
    phone_e164 = models.CharField("telefone", max_length=20, blank=True, default="")
    email = models.EmailField("e-mail", blank=True, default="")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    notes = models.TextField("observações", blank=True, default="")

    class Meta:
        verbose_name = "cliente"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "cpf_cnpj"],
                condition=~models.Q(cpf_cnpj=""),
                name="client_document_unique_per_tenant",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "phone_e164"], name="client_tenant_phone_idx"),
            models.Index(fields=["tenant", "name"], name="client_tenant_name_idx"),
        ]

    def __str__(self) -> str:
        return self.name


class ClientTermAcceptance(TenantModel):
    """Registro de aceite do termo de ciência de IA. Append-only: nunca é alterado."""

    class Channel(models.TextChoices):
        WHATSAPP = "WHATSAPP", "WhatsApp"
        IN_PERSON = "IN_PERSON", "Presencial"
        EMAIL = "EMAIL", "E-mail"
        OTHER = "OTHER", "Outro"

    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="term_acceptances")
    term_version = models.ForeignKey(
        "tenants.ClientTermVersion", on_delete=models.PROTECT, related_name="+"
    )
    accepted_at = models.DateTimeField("aceito em")
    channel = models.CharField(max_length=10, choices=Channel.choices)
    # Referência da prova (ex.: id da mensagem no WhatsApp, "assinado em papel, pasta 12").
    evidence = models.CharField("evidência", max_length=255, blank=True, default="")
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = "aceite do termo de ciência"
        ordering = ["-accepted_at"]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValueError("Aceite do termo é imutável.")
        super().save(*args, **kwargs)

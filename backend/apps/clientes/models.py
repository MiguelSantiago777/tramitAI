from typing import Any

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower

from apps.core.models import ActiveTenantManager, SoftDeletable, TenantManager, TenantModel


class Client(SoftDeletable, TenantModel):
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

    # Apagado de vez, mas com aceite do termo de IA (prova, append-only): a linha fica sem
    # nenhum dado pessoal e nunca mais aparece (nem na lixeira).
    anonymized_at = models.DateTimeField(null=True, blank=True, editable=False)

    objects: ActiveTenantManager[Any] = ActiveTenantManager()
    # Inclui os que estão na lixeira (unicidade, lixeira, restauração).
    with_deleted: TenantManager[Any] = TenantManager()

    class Meta:
        verbose_name = "cliente"
        default_manager_name = "objects"
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


class ClientNote(TenantModel):
    """Registro de atendimento (ligação, reunião, anotação) na ficha do cliente."""

    class Kind(models.TextChoices):
        NOTE = "NOTE", "Anotação"
        CALL = "CALL", "Ligação"
        MEETING = "MEETING", "Reunião"
        VISIT = "VISIT", "Atendimento presencial"

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="service_notes")
    legal_case = models.ForeignKey(
        "processos.LegalCase",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.NOTE)
    body = models.TextField("texto")
    author = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = "registro de atendimento"
        indexes = [models.Index(fields=["client", "-created_at"], name="client_note_recent_idx")]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.created_at:%d/%m/%Y}"


class Tag(TenantModel):
    """Etiqueta do escritório (ex.: Trabalhista, VIP, Indicação)."""

    class Color(models.TextChoices):
        INDIGO = "indigo", "Índigo"
        GREEN = "green", "Verde"
        AMBER = "amber", "Amarelo"
        RED = "red", "Vermelho"
        TEAL = "teal", "Azul-petróleo"
        PINK = "pink", "Rosa"
        SLATE = "slate", "Cinza"

    name = models.CharField("nome", max_length=40)
    color = models.CharField(max_length=10, choices=Color.choices, default=Color.INDIGO)

    class Meta:
        verbose_name = "etiqueta"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint("tenant", Lower("name"), name="tag_name_unique_per_tenant"),
        ]

    def __str__(self) -> str:
        return self.name


class ClientTag(TenantModel):
    """Cliente ↔ etiqueta. Tabela explícita (com tenant e RLS), não M2M automático."""

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="client_tags")
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name="client_tags")

    class Meta:
        verbose_name = "etiqueta do cliente"
        constraints = [
            models.UniqueConstraint(fields=["client", "tag"], name="client_tag_unique"),
        ]

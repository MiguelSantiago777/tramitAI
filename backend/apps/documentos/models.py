"""Documentos do escritório: arquivos enviados pela equipe e mídias recebidas no WhatsApp.

Os arquivos ficam no storage padrão (volume privado). Nunca há link público: o download passa
pela API, com login e RLS, e cada download é auditado.
"""

import uuid
from pathlib import PurePosixPath
from typing import Any

from django.conf import settings
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.models import TenantModel


def document_path(instance: Document, filename: str) -> str:
    """<tenant>/<ano>/<mês>/<uuid><ext>: o nome original fica só no banco."""
    suffix = PurePosixPath(filename).suffix.lower()[:10]
    return f"{instance.tenant_id}/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{suffix}"


class Document(TenantModel):
    class Category(models.TextChoices):
        PESSOAL = "PESSOAL", "Documento pessoal"
        COMPROVANTE = "COMPROVANTE", "Comprovante"
        CONTRATO = "CONTRATO", "Contrato / procuração"
        PECA = "PECA", "Peça processual"
        DECISAO = "DECISAO", "Decisão / sentença"
        PROVA = "PROVA", "Prova"
        WHATSAPP = "WHATSAPP", "Recebido no WhatsApp"
        OUTRO = "OUTRO", "Outro"

    class Source(models.TextChoices):
        UPLOAD = "UPLOAD", "Enviado pela equipe"
        WHATSAPP = "WHATSAPP", "WhatsApp"

    file = models.FileField(upload_to=document_path, max_length=255)
    name = models.CharField("nome", max_length=255)
    content_type = models.CharField(max_length=100)
    size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    category = models.CharField(max_length=12, choices=Category.choices, default=Category.OUTRO)
    description = models.CharField("descrição", max_length=500, blank=True, default="")
    source = models.CharField(max_length=8, choices=Source.choices, default=Source.UPLOAD)

    client = models.ForeignKey(
        "clientes.Client",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="documents",
    )
    legal_case = models.ForeignKey(
        "processos.LegalCase",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
    )
    conversation = models.ForeignKey(
        "whatsapp.Conversation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
    )
    message = models.OneToOneField(
        "whatsapp.Message",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = "documento"
        verbose_name_plural = "documentos"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "client", "-created_at"], name="document_client_idx"),
            models.Index(fields=["tenant", "legal_case", "-created_at"], name="document_case_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(client__isnull=False)
                | Q(legal_case__isnull=False)
                | Q(conversation__isnull=False),
                name="document_has_owner",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        storage, path = self.file.storage, self.file.name
        result = super().delete(*args, **kwargs)
        if path:
            # Apaga o arquivo só depois do commit: se a transação voltar, o arquivo continua.
            transaction.on_commit(lambda: storage.delete(path))
        return result

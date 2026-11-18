"""Financeiro do escritório: contratos de honorários, parcelas e cobrança pelo Mercado Pago."""

import secrets
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TenantModel

# ======================================================================== control plane (sem RLS)


def _route_token() -> str:
    return secrets.token_urlsafe(24)


class PaymentWebhookRoute(models.Model):
    """Token da URL de aviso do Mercado Pago → escritório (lido antes de existir tenant ativo).

    Só roteamento. O aviso nunca dá baixa sozinho: o pagamento é consultado na API do MP com o
    token do escritório (guardado em MercadoPagoAccount, com RLS).
    """

    token = models.CharField(max_length=64, primary_key=True, default=_route_token)
    tenant = models.OneToOneField("tenants.Tenant", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "rota de aviso do Mercado Pago"

    def __str__(self) -> str:
        return str(self.tenant_id)


# ======================================================================== data plane (RLS)


class MercadoPagoAccount(TenantModel):
    """Conta do Mercado Pago do escritório (o dinheiro cai direto nela)."""

    access_token_encrypted = models.TextField()
    mp_user_id = models.CharField(max_length=32)
    nickname = models.CharField(max_length=120, blank=True, default="")
    connected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )

    class Meta:
        verbose_name = "conta do Mercado Pago"
        constraints = [
            models.UniqueConstraint(fields=["tenant"], name="mercadopago_one_per_tenant"),
        ]

    def __str__(self) -> str:
        return self.nickname or self.mp_user_id


class FeeAgreement(TenantModel):
    """Contrato de honorários com um cliente, dividido em parcelas."""

    class Kind(models.TextChoices):
        CONTRATUAL = "CONTRATUAL", "Honorários contratuais"
        EXITO = "EXITO", "Honorários de êxito"
        MENSAL = "MENSAL", "Mensalidade / partido"
        CONSULTA = "CONSULTA", "Consulta"
        OUTRO = "OUTRO", "Outro"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Em andamento"
        FINISHED = "FINISHED", "Quitado"
        CANCELLED = "CANCELLED", "Cancelado"

    client = models.ForeignKey(
        "clientes.Client", on_delete=models.PROTECT, related_name="fee_agreements"
    )
    legal_case = models.ForeignKey(
        "processos.LegalCase",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fee_agreements",
    )
    title = models.CharField("descrição", max_length=200)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.CONTRATUAL)
    total_amount = models.DecimalField("valor total", max_digits=12, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    notes = models.TextField("observações", blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )

    class Meta:
        verbose_name = "contrato de honorários"
        verbose_name_plural = "contratos de honorários"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title


class Installment(TenantModel):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Em aberto"
        PAID = "PAID", "Paga"
        CANCELLED = "CANCELLED", "Cancelada"

    class Method(models.TextChoices):
        PIX = "PIX", "Pix"
        BOLETO = "BOLETO", "Boleto"
        CARTAO = "CARTAO", "Cartão"
        TRANSFERENCIA = "TRANSFERENCIA", "Transferência"
        DINHEIRO = "DINHEIRO", "Dinheiro"
        OUTRO = "OUTRO", "Outro"

    class ChargeKind(models.TextChoices):
        NONE = "", "Sem cobrança"
        PIX = "PIX", "Pix"
        LINK = "LINK", "Link de pagamento"

    agreement = models.ForeignKey(
        FeeAgreement, on_delete=models.CASCADE, related_name="installments"
    )
    number = models.PositiveSmallIntegerField()
    due_date = models.DateField("vencimento")
    amount = models.DecimalField("valor", max_digits=12, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)

    paid_at = models.DateTimeField(null=True, blank=True)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    method = models.CharField(max_length=14, choices=Method.choices, blank=True, default="")
    paid_note = models.CharField(max_length=255, blank=True, default="")
    settled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    # Cobrança aberta no Mercado Pago (no máximo uma por vez).
    charge_kind = models.CharField(max_length=4, choices=ChargeKind.choices, blank=True, default="")
    mp_payment_id = models.CharField(max_length=32, blank=True, default="", db_index=True)
    mp_preference_id = models.CharField(max_length=64, blank=True, default="")
    pix_code = models.TextField(blank=True, default="")
    pix_qr_base64 = models.TextField(blank=True, default="")
    payment_url = models.URLField(max_length=500, blank=True, default="")
    charge_expires_at = models.DateTimeField(null=True, blank=True)
    last_reminder_on = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "parcela"
        ordering = ["due_date", "number"]
        constraints = [
            models.UniqueConstraint(
                fields=["agreement", "number"], name="installment_number_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="installment_amount_gt_0"
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status", "due_date"], name="installment_due_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.agreement} {self.number}"

    @property
    def is_overdue(self) -> bool:
        return self.status == self.Status.OPEN and self.due_date < timezone.localdate()

    @property
    def has_active_charge(self) -> bool:
        if not self.charge_kind or self.status != self.Status.OPEN:
            return False
        return self.charge_expires_at is None or self.charge_expires_at > timezone.now()


def overdue_days(due: date) -> int:
    return max((timezone.localdate() - due).days, 0)


ZERO = Decimal("0.00")

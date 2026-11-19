"""Assinatura do TramitAI pelos escritórios (control plane: sem RLS, só a plataforma mexe).

O escritório paga para a conta do TramitAI no Mercado Pago (assinatura recorrente mensal).
"""

from datetime import datetime, timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class Plan(models.Model):
    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField("nome", max_length=100)
    price = models.DecimalField("preço mensal (R$)", max_digits=10, decimal_places=2)
    description = models.TextField("descrição", blank=True, default="")
    max_users = models.PositiveSmallIntegerField(
        "máximo de usuários", null=True, blank=True, help_text="Vazio = sem limite."
    )
    monthly_ai_limit = models.PositiveIntegerField(
        "mensagens da Lia por mês", null=True, blank=True, help_text="Vazio = sem limite."
    )
    includes_publications = models.BooleanField("publicações do Diário (DJEN)", default=False)
    is_active = models.BooleanField("disponível para assinar", default=True)
    sort = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "plano"
        ordering = ["sort", "price"]

    def __str__(self) -> str:
        return f"{self.name} (R$ {self.price})"


class Subscription(models.Model):
    class Status(models.TextChoices):
        TRIAL = "TRIAL", "Teste grátis"
        PENDING = "PENDING", "Aguardando pagamento"
        ACTIVE = "ACTIVE", "Ativa"
        PAST_DUE = "PAST_DUE", "Pagamento atrasado"
        CANCELLED = "CANCELLED", "Cancelada"
        EXEMPT = "EXEMPT", "Isenta (cortesia/manual)"

    tenant = models.OneToOneField(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="subscription"
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.TRIAL)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    # Acesso pago até aqui (próxima cobrança do MP). Depois disso, tolerância e bloqueio.
    paid_until = models.DateTimeField(null=True, blank=True)
    payer_email = models.EmailField(blank=True, default="")
    mp_preapproval_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    mp_status = models.CharField(max_length=20, blank=True, default="")
    mp_init_point = models.URLField(max_length=500, blank=True, default="")
    notes = models.TextField("observações internas", blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "assinatura"

    def __str__(self) -> str:
        return f"{self.tenant_id} {self.status}"

    def access_until(self) -> datetime | None:
        """Até quando o escritório pode usar. None = sem limite (isento)."""
        if self.status == self.Status.EXEMPT:
            return None
        grace = timedelta(days=settings.SUBSCRIPTION_GRACE_DAYS)
        candidates = []
        if self.trial_ends_at:
            candidates.append(self.trial_ends_at)
        if self.paid_until:
            candidates.append(self.paid_until + grace)
        return max(candidates) if candidates else timezone.now() - timedelta(seconds=1)

    def is_blocked(self, now: datetime | None = None) -> bool:
        until = self.access_until()
        return until is not None and (now or timezone.now()) >= until


class SubscriptionPayment(models.Model):
    """Cada cobrança da assinatura (Mercado Pago) ou pagamento lançado à mão no painel."""

    class Source(models.TextChoices):
        MERCADOPAGO = "MERCADOPAGO", "Mercado Pago"
        MANUAL = "MANUAL", "Lançado no painel"

    class Status(models.TextChoices):
        PAID = "PAID", "Pago"
        FAILED = "FAILED", "Recusado"
        PENDING = "PENDING", "Em processamento"

    subscription = models.ForeignKey(
        Subscription, on_delete=models.CASCADE, related_name="payments"
    )
    source = models.CharField(max_length=12, choices=Source.choices)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PAID)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_at = models.DateTimeField()
    # Id da cobrança no MP (vazio no manual). Único: o aviso pode chegar mais de uma vez.
    mp_payment_id = models.CharField(max_length=64, blank=True, default="")
    note = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "pagamento de assinatura"
        ordering = ["-paid_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["mp_payment_id"],
                condition=~models.Q(mp_payment_id=""),
                name="subscription_payment_mp_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.subscription_id} {self.amount} {self.paid_at:%d/%m/%Y}"

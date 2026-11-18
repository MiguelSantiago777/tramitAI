"""Acompanhamentos do escritório: tarefas, prazos e agenda (audiências, reuniões).

Regra do projeto: o sistema nunca inventa prazo. Tarefas criadas a partir de andamentos
(intimação, citação...) só pedem para o advogado VERIFICAR e registrar a data limite.
"""

from django.conf import settings
from django.db import models

from apps.core.models import TenantModel


class Task(TenantModel):
    class Kind(models.TextChoices):
        TASK = "TASK", "Tarefa"
        DEADLINE = "DEADLINE", "Prazo"
        FOLLOW_UP = "FOLLOW_UP", "Retorno ao cliente"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Aberta"
        DONE = "DONE", "Concluída"
        CANCELED = "CANCELED", "Cancelada"

    class Priority(models.TextChoices):
        LOW = "LOW", "Baixa"
        NORMAL = "NORMAL", "Normal"
        HIGH = "HIGH", "Alta"

    class Source(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        MOVEMENT = "MOVEMENT", "Andamento do processo"

    title = models.CharField("título", max_length=200)
    description = models.TextField("descrição", blank=True, default="")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.TASK)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    priority = models.CharField(max_length=8, choices=Priority.choices, default=Priority.NORMAL)
    due_date = models.DateField("data", null=True, blank=True)
    due_time = models.TimeField("hora", null=True, blank=True)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="responsável",
    )
    client = models.ForeignKey(
        "clientes.Client", on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks"
    )
    legal_case = models.ForeignKey(
        "processos.LegalCase",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
    )
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUAL)
    source_movement = models.ForeignKey(
        "processos.CaseMovement",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = "tarefa"
        constraints = [
            # Uma tarefa automática por andamento (sincronização repetida não duplica).
            models.UniqueConstraint(
                fields=["tenant", "source_movement"],
                condition=models.Q(source_movement__isnull=False),
                name="task_one_per_movement",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status", "due_date"], name="task_status_due_idx"),
            models.Index(fields=["tenant", "assignee", "status"], name="task_assignee_idx"),
        ]

    def __str__(self) -> str:
        return self.title


class Event(TenantModel):
    class Kind(models.TextChoices):
        HEARING = "HEARING", "Audiência"
        MEETING = "MEETING", "Reunião"
        CONSULTATION = "CONSULT", "Atendimento"
        OTHER = "OTHER", "Outro"

    class Status(models.TextChoices):
        PENDING = "PENDING", "A confirmar"
        SCHEDULED = "SCHEDULED", "Agendado"
        DONE = "DONE", "Realizado"
        CANCELED = "CANCELED", "Cancelado"

    title = models.CharField("título", max_length=200)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.MEETING)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SCHEDULED)
    starts_at = models.DateTimeField("início")
    ends_at = models.DateTimeField("fim", null=True, blank=True)
    location = models.CharField("local", max_length=255, blank=True, default="")
    notes = models.TextField("observações", blank=True, default="")
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="responsável",
    )
    client = models.ForeignKey(
        "clientes.Client", on_delete=models.SET_NULL, null=True, blank=True, related_name="events"
    )
    legal_case = models.ForeignKey(
        "processos.LegalCase",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    # Cópia no Google Agenda do responsável (se ele conectou).
    google_event_id = models.CharField(max_length=128, blank=True, default="", editable=False)
    # Lembrete ao cliente pelo WhatsApp na véspera (vira rascunho para aprovação).
    remind_client = models.BooleanField("lembrar o cliente", default=False)
    client_reminded_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = "compromisso"
        indexes = [
            models.Index(fields=["tenant", "starts_at"], name="event_starts_idx"),
        ]

    def __str__(self) -> str:
        return self.title


class GoogleCalendarConnection(TenantModel):
    """Google Agenda conectado por um advogado (autorização dele, token cifrado)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    google_email = models.EmailField(blank=True, default="")
    calendar_id = models.CharField(max_length=255, default="primary")
    refresh_token_encrypted = models.TextField()
    # Autorização vencida/revogada no Google: a tela pede para reconectar.
    needs_reconnect = models.BooleanField(default=False)
    # Só livre/ocupado dos próximos dias: [[início, fim], ...] em ISO. Nada de títulos.
    busy_cache = models.JSONField(default=list, blank=True)
    busy_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Google Agenda conectado"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "user"], name="google_calendar_one_per_user"),
        ]

    def __str__(self) -> str:
        return self.google_email or str(self.user_id)

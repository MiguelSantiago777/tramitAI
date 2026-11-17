from django.conf import settings
from django.db import models

from apps.core.models import TenantModel

# ======================================================================== control plane (sem RLS)


class PhoneNumberRoute(models.Model):
    """phone_number_id da Meta → escritório. Lido pelo worker antes de existir tenant ativo.

    Só roteamento: as credenciais ficam em WhatsAppAccount, que tem RLS.
    """

    phone_number_id = models.CharField(max_length=64, primary_key=True)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "rota de número do WhatsApp"

    def __str__(self) -> str:
        return self.phone_number_id


class InboundWebhookEvent(models.Model):
    """Payload bruto do webhook, gravado antes de qualquer processamento.

    Contém conteúdo de mensagens: é expurgado após WEBHOOK_EVENT_RETENTION_DAYS do processamento.
    Nunca logar `payload`.
    """

    class Source(models.TextChoices):
        META = "meta", "Meta (Cloud API)"
        BRIDGE = "bridge", "Ponte Baileys"

    id = models.BigAutoField(primary_key=True)
    source = models.CharField(max_length=8, choices=Source.choices, default=Source.META)
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    # Só códigos/descrições técnicas, nunca conteúdo.
    last_error = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        verbose_name = "evento de webhook"
        indexes = [models.Index(fields=["processed_at"], name="webhook_event_processed_idx")]

    def __str__(self) -> str:
        # Nunca o payload.
        return f"evento {self.pk}"


# ======================================================================== data plane (com RLS)


class WhatsAppAccount(TenantModel):
    """Número de WhatsApp do escritório.

    Dois provedores: CLOUD_API (oficial da Meta, onboarding manual) e BAILEYS (WhatsApp Web
    via ponte, pareado por QR Code). No Baileys, `phone_number_id` é o id da sessão na ponte.
    """

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Ativo"
        DISABLED = "DISABLED", "Desativado"

    class Provider(models.TextChoices):
        CLOUD_API = "CLOUD_API", "WhatsApp Cloud API (Meta)"
        BAILEYS = "BAILEYS", "WhatsApp Web (Baileys)"

    class Connection(models.TextChoices):
        PENDING = "PENDING", "Aguardando pareamento"
        CONNECTED = "CONNECTED", "Conectado"
        RECONNECTING = "RECONNECTING", "Reconectando"
        LOGGED_OUT = "LOGGED_OUT", "Desconectado"

    provider = models.CharField(max_length=10, choices=Provider.choices, default=Provider.CLOUD_API)
    # Último estado informado pela ponte (Baileys). Cloud API fica sempre CONNECTED.
    connection = models.CharField(
        max_length=12, choices=Connection.choices, default=Connection.CONNECTED
    )
    phone_number_id = models.CharField(max_length=64, unique=True)
    waba_id = models.CharField(max_length=64, blank=True, default="")
    display_phone = models.CharField(max_length=32, blank=True, default="")
    # Token da Cloud API cifrado com apps.core.crypto. Nunca sai pela API nem por log.
    # Vazio no Baileys (o segredo da sessão fica no volume da ponte).
    access_token_encrypted = models.TextField(blank=True, default="")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    # Modelo (template) utility aprovado na WABA do escritório para avisar de andamento fora da
    # janela de 24h. Texto esperado em apps/whatsapp/templates.py (o README explica como criar).
    movement_template_name = models.CharField(
        max_length=64, blank=True, default="atualizacao_processo"
    )
    template_language = models.CharField(max_length=10, default="pt_BR")

    class Meta:
        verbose_name = "conta de WhatsApp"


class Conversation(TenantModel):
    """Conversa com um contato (um wa_id) num número do escritório."""

    class Status(models.TextChoices):
        OPEN = "OPEN", "Aberta"
        CLOSED = "CLOSED", "Encerrada"

    account = models.ForeignKey(WhatsAppAccount, on_delete=models.PROTECT, related_name="+")
    client = models.ForeignKey(
        "clientes.Client",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conversations",
    )
    wa_id = models.CharField(max_length=32)
    contact_name = models.CharField(max_length=200, blank=True, default="")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    # Janela de atendimento de 24h da Meta conta a partir da última mensagem do contato.
    last_inbound_at = models.DateTimeField(null=True, blank=True)
    last_message_at = models.DateTimeField(null=True, blank=True)
    unread_count = models.PositiveIntegerField(default=0)
    # Cliente encontrado pelo CPF digitado na conversa. Só sugestão: CPF não prova identidade,
    # então o vínculo depende de confirmação humana.
    suggested_client = models.ForeignKey(
        "clientes.Client",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    # Versão do termo de ciência oferecida nesta conversa (rascunho criado).
    ai_consent_version = models.PositiveIntegerField(null=True, blank=True)
    # Quem da equipe cuida desta conversa (inbox de equipe).
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="responsável",
    )

    class Meta:
        verbose_name = "conversa"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "account", "wa_id"], name="conversation_unique_contact"
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "-last_message_at"], name="conversation_recent_idx"),
        ]


class Message(TenantModel):
    class Direction(models.TextChoices):
        INBOUND = "IN", "Recebida"
        OUTBOUND = "OUT", "Enviada"

    class Type(models.TextChoices):
        TEXT = "text", "Texto"
        IMAGE = "image", "Imagem"
        AUDIO = "audio", "Áudio"
        VIDEO = "video", "Vídeo"
        DOCUMENT = "document", "Documento"
        STICKER = "sticker", "Figurinha"
        LOCATION = "location", "Localização"
        TEMPLATE = "template", "Modelo aprovado"
        OTHER = "other", "Outro"

    class Status(models.TextChoices):
        RECEIVED = "RECEIVED", "Recebida"
        QUEUED = "QUEUED", "Na fila"
        SENDING = "SENDING", "Enviando"
        SENT = "SENT", "Enviada"
        DELIVERED = "DELIVERED", "Entregue"
        READ = "READ", "Lida"
        FAILED = "FAILED", "Falhou"

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    direction = models.CharField(max_length=3, choices=Direction.choices)
    # Id da Meta (wamid). Único global: chave de idempotência do webhook.
    wa_message_id = models.CharField(max_length=128, unique=True, null=True, blank=True)
    type = models.CharField(max_length=10, choices=Type.choices, default=Type.TEXT)
    body = models.TextField(blank=True, default="")
    media_id = models.CharField(max_length=128, blank=True, default="")
    # Só para type=template. `body` guarda a prévia renderizada, para o inbox.
    template_name = models.CharField(max_length=64, blank=True, default="")
    template_language = models.CharField(max_length=10, blank=True, default="")
    template_params = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices)
    error_code = models.CharField(max_length=32, blank=True, default="")
    error_detail = models.CharField(max_length=255, blank=True, default="")
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    # Horário informado pela Meta (mensagem recebida) ou do aceite pela API (enviada).
    wa_timestamp = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "mensagem"
        indexes = [
            models.Index(fields=["conversation", "created_at"], name="message_thread_idx"),
        ]

    def __str__(self) -> str:
        # Sem conteúdo: __str__ aparece em logs e no admin.
        return f"{self.direction} {self.type} {self.status}"


# Ordem de progresso dos status de saída; webhooks podem chegar fora de ordem.
OUTBOUND_STATUS_RANK: dict[str, int] = {
    Message.Status.QUEUED: 0,
    Message.Status.SENDING: 1,
    Message.Status.SENT: 2,
    Message.Status.DELIVERED: 3,
    Message.Status.READ: 4,
}


class QuickReply(TenantModel):
    """Resposta pronta do escritório (texto escrito por pessoa, não pela IA).

    `{nome}` no texto vira o primeiro nome do cliente na hora de usar.
    """

    title = models.CharField("título", max_length=80)
    body = models.TextField("texto")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = "resposta pronta"
        ordering = ["title"]

    def __str__(self) -> str:
        return self.title

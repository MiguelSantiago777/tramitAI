"""Settings comuns. Tudo que é segredo ou varia por ambiente vem de variável de ambiente."""

from datetime import timedelta
from pathlib import Path

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()

SECRET_KEY: str = env("DJANGO_SECRET_KEY")
DEBUG: bool = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS: list[str] = env.list("DJANGO_ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS: list[str] = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "drf_spectacular",
    "apps.core",
    "apps.tenants",
    "apps.accounts",
    "apps.clientes",
    "apps.processos",
    "apps.whatsapp",
    "apps.ia",
    "apps.aprovacoes",
    "apps.agenda",
    "apps.funil",
    "apps.documentos",
    "apps.financeiro",
    "apps.relatorios",
    "apps.cobranca",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Estáticos do admin servidos pelo próprio Django (sem nginx só para isso).
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.TenantContextMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --------------------------------------------------------------------------- banco
# DATABASE_URL usa o role tramitai_app (sem BYPASSRLS). Migrations rodam com DATABASE_OWNER_URL.
DATABASES = {"default": env.db("DATABASE_URL")}
# Cada request roda numa transação: necessário porque o tenant é setado com
# set_config(..., is_local=true), que só vale dentro da transação corrente.
DATABASES["default"]["ATOMIC_REQUESTS"] = True
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

# Role que recebe os GRANTs de DML depois de cada migrate (ver apps.core.apps).
DB_APP_ROLE: str = env("DB_APP_ROLE", default="tramitai_app")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Arquivos dos clientes (documentos e mídias do WhatsApp). Privados: só saem pela API com
# login (não existe rota pública em MEDIA_URL). Em produção é um volume do Docker.
MEDIA_ROOT = env.path("MEDIA_ROOT", default=BASE_DIR / "media")
DOCUMENT_MAX_BYTES: int = env.int("DOCUMENT_MAX_BYTES", default=25 * 1024 * 1024)
DATA_UPLOAD_MAX_MEMORY_SIZE = 2_621_440
FILE_UPLOAD_MAX_MEMORY_SIZE = 2_621_440
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# --------------------------------------------------------------------------- e-mail
# Em dev, o e-mail aparece no log do backend. Em produção: EMAIL_URL=smtp+tls://user:senha@host:587
EMAIL_CONFIG = env.email_url("EMAIL_URL", default="consolemail://")
vars().update(EMAIL_CONFIG)
DEFAULT_FROM_EMAIL: str = env(
    "DEFAULT_FROM_EMAIL", default="TramitAI <nao-responda@tramitai.local>"
)
# Endereço público do app, para links nos e-mails (ex.: redefinir senha).
FRONTEND_URL: str = env("FRONTEND_URL", default="http://localhost:4200")
# Link de criar/redefinir senha (convite e esqueci a senha). Uso único: troca a senha, expira.
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24 * 3  # 3 dias

# --------------------------------------------------------------------------- DRF
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.accounts.authentication.TenantJWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_THROTTLE_RATES": {
        "login": env("LOGIN_THROTTLE_RATE", default="10/min"),
        "password_reset": env("PASSWORD_RESET_THROTTLE_RATE", default="5/hour"),
        "signup": env("SIGNUP_THROTTLE_RATE", default="5/hour"),
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_MINUTES", default=15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_DAYS", default=7)),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "UPDATE_LAST_LOGIN": False,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "TramitAI API",
    "DESCRIPTION": "API do TramitAI, secretária jurídica no WhatsApp.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    # Dois campos "role" com choices diferentes: nomes explícitos para o frontend.
    "ENUM_NAME_OVERRIDES": {
        "MembershipRoleEnum": "apps.accounts.models.Membership.Role",
        "CaseClientRoleEnum": "apps.processos.models.CaseClient.Role",
        "ClientStatusEnum": "apps.clientes.models.Client.Status",
        "CaseStatusEnum": "apps.processos.models.LegalCase.Status",
        "ConversationStatusEnum": "apps.whatsapp.models.Conversation.Status",
        "MessageStatusEnum": "apps.whatsapp.models.Message.Status",
        "DraftStatusEnum": "apps.aprovacoes.models.OutboundDraft.Status",
        "TenantStatusEnum": "apps.tenants.models.Tenant.Status",
        "SyncStatusEnum": "apps.processos.models.LegalCase.SyncStatus",
        "MovementNotificationEnum": "apps.processos.models.CaseMovement.Notification",
        "TaskStatusEnum": "apps.agenda.models.Task.Status",
        "TaskKindEnum": "apps.agenda.models.Task.Kind",
        "EventStatusEnum": "apps.agenda.models.Event.Status",
        "EventKindEnum": "apps.agenda.models.Event.Kind",
        "OpportunityStageEnum": "apps.funil.models.Opportunity.Stage",
        "OpportunityAreaEnum": "apps.funil.models.Opportunity.Area",
        "OpportunitySourceEnum": "apps.funil.models.Opportunity.Source",
        "TagColorEnum": "apps.clientes.models.Tag.Color",
    },
}

# --------------------------------------------------------------------------- Celery
CELERY_BROKER_URL: str = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = None
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE: dict[str, dict[str, object]] = {
    "purge-webhook-events": {
        "task": "apps.whatsapp.tasks.purge_processed_webhook_events",
        "schedule": 60 * 60 * 6,
    },
    "fail-stuck-outbound-messages": {
        "task": "apps.whatsapp.tasks.fail_stuck_outbound_messages",
        "schedule": 60 * 5,
    },
    "event-reminders": {
        "task": "apps.agenda.tasks.create_event_reminders",
        "schedule": 60 * 60,
    },
    "schedule-case-checks": {
        "task": "apps.processos.tasks.schedule_case_checks",
        "schedule": 60 * 60,
    },
    # Diário (DJEN): busca as publicações das OABs monitoradas a cada 2h.
    "schedule-publication-checks": {
        "task": "apps.processos.tasks.schedule_publication_checks",
        "schedule": 60 * 60 * 2,
    },
    # 9h de Brasília: lembretes de parcela viram rascunho para aprovação.
    "payment-reminders": {
        "task": "apps.financeiro.tasks.create_payment_reminders",
        "schedule": crontab(hour=12, minute=0),
    },
    "refresh-google-busy": {
        "task": "apps.agenda.tasks.refresh_google_busy",
        "schedule": 60 * 10,
    },
    # Confere as assinaturas no Mercado Pago (cobre aviso perdido).
    "refresh-subscriptions": {
        "task": "apps.cobranca.tasks.refresh_subscriptions",
        "schedule": crontab(hour=9, minute=30),
    },
}

# --------------------------------------------------------------------------- Mercado Pago
# "http" (API real) ou "fake" (dev/testes). Cada escritório usa o próprio access token
# (financeiro); a assinatura do TramitAI usa MERCADOPAGO_PLATFORM_TOKEN (cobranca).
MERCADOPAGO_CLIENT: str = env("MERCADOPAGO_CLIENT", default="fake")
MERCADOPAGO_API_URL: str = env("MERCADOPAGO_API_URL", default="https://api.mercadopago.com")
MERCADOPAGO_TIMEOUT: float = env.float("MERCADOPAGO_TIMEOUT", default=20.0)
MERCADOPAGO_STATEMENT: str = env("MERCADOPAGO_STATEMENT", default="HONORARIOS")
# Assinatura do TramitAI: token da SUA conta do Mercado Pago (quem recebe dos escritórios).
MERCADOPAGO_PLATFORM_TOKEN: str = env("MERCADOPAGO_PLATFORM_TOKEN", default="")
SIGNUP_ENABLED: bool = env.bool("SIGNUP_ENABLED", default=True)
TRIAL_DAYS: int = env.int("TRIAL_DAYS", default=14)
# Dias de tolerância depois do vencimento antes de bloquear o acesso.
SUBSCRIPTION_GRACE_DAYS: int = env.int("SUBSCRIPTION_GRACE_DAYS", default=5)
# Google Agenda: "http" (Google de verdade) ou "fake" (dev/testes). Credenciais OAuth do
# projeto do TramitAI no Google Cloud (ver README, seção Google Agenda).
GOOGLE_CALENDAR_CLIENT: str = env("GOOGLE_CALENDAR_CLIENT", default="fake")
GOOGLE_CLIENT_ID: str = env("GOOGLE_CLIENT_ID", default="")
GOOGLE_CLIENT_SECRET: str = env("GOOGLE_CLIENT_SECRET", default="")
# Endereço público da API (o MP chama de volta aqui). Padrão: o mesmo domínio do site.
PUBLIC_API_URL: str = env("PUBLIC_API_URL", default=FRONTEND_URL)

# --------------------------------------------------------------------------- segredos
# Chaves Fernet (urlsafe base64, 32 bytes) separadas por vírgula. A primeira cifra; todas
# decifram (permite rotação). Gere com:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FIELD_ENCRYPTION_KEYS: list[str] = env.list("FIELD_ENCRYPTION_KEYS", default=[])

# --------------------------------------------------------------------------- WhatsApp
# App único do TramitAI na Meta: o App Secret valida a assinatura antes de saber o tenant.
WHATSAPP_APP_SECRET: str = env("WHATSAPP_APP_SECRET", default="")
WHATSAPP_VERIFY_TOKEN: str = env("WHATSAPP_VERIFY_TOKEN", default="")
# "cloud_api" (Meta) ou "fake" (dev/testes: não envia nada para fora).
WHATSAPP_GATEWAY: str = env("WHATSAPP_GATEWAY", default="fake")
WHATSAPP_GRAPH_URL: str = env("WHATSAPP_GRAPH_URL", default="https://graph.facebook.com")
WHATSAPP_GRAPH_VERSION: str = env("WHATSAPP_GRAPH_VERSION", default="v24.0")
WHATSAPP_HTTP_TIMEOUT: float = env.float("WHATSAPP_HTTP_TIMEOUT", default=10.0)
# Ponte Baileys (WhatsApp Web, não oficial). Uma sessão por escritório no serviço `bridge`.
WHATSAPP_BRIDGE_URL: str = env("WHATSAPP_BRIDGE_URL", default="http://bridge:3100")
WHATSAPP_BRIDGE_SECRET: str = env("WHATSAPP_BRIDGE_SECRET", default="")
# "bridge" (ponte real) ou "fake" (testes).
WHATSAPP_BAILEYS_GATEWAY: str = env("WHATSAPP_BAILEYS_GATEWAY", default="bridge")
WHATSAPP_BRIDGE_TIMEOUT: float = env.float("WHATSAPP_BRIDGE_TIMEOUT", default=30.0)
# Payload bruto do webhook contém mensagens: guardar só o necessário para reprocessar.
WEBHOOK_EVENT_RETENTION_DAYS: int = env.int("WEBHOOK_EVENT_RETENTION_DAYS", default=7)

# --------------------------------------------------------------------------- IA
# "fake" (dev/testes, determinístico, não sai da máquina) ou "anthropic".
LLM_PROVIDER: str = env("LLM_PROVIDER", default="fake")
_DEFAULT_MODELS = {"anthropic": "claude-sonnet-5-5", "gemini": "gemini-3.8-flash"}
LLM_MODEL: str = env("LLM_MODEL", default=_DEFAULT_MODELS.get(LLM_PROVIDER, "fake"))
GEMINI_API_KEY: str = env("GEMINI_API_KEY", default="")
# Modelos reserva (separados por vírgula), tentados na hora se o principal estiver
# sobrecarregado. Ex.: LLM_FALLBACK_MODELS=gemini-3.8-flash-lite
LLM_FALLBACK_MODELS: list[str] = env.list("LLM_FALLBACK_MODELS", default=[])
# Raciocínio do Gemini 3: "minimal" ou "low" deixa a triagem mais rápida. Vazio = padrão do Google.
LLM_THINKING_LEVEL: str = env("LLM_THINKING_LEVEL", default="")
LLM_EFFORT: str = env("LLM_EFFORT", default="medium")
LLM_MAX_TOKENS: int = env.int("LLM_MAX_TOKENS", default=16000)
LLM_TIMEOUT_SECONDS: float = env.float("LLM_TIMEOUT_SECONDS", default=40.0)
# Fallback automático do servidor quando o modelo recusa (só provedor anthropic).
LLM_REFUSAL_FALLBACK: bool = env.bool("LLM_REFUSAL_FALLBACK", default=True)
# Espera antes da triagem, para juntar mensagens enviadas em sequência.
TRIAGE_DEBOUNCE_SECONDS: int = env.int("TRIAGE_DEBOUNCE_SECONDS", default=8)
TRIAGE_HISTORY_MESSAGES: int = env.int("TRIAGE_HISTORY_MESSAGES", default=20)

# --------------------------------------------------------------------------- andamentos
# "fake" (dev/testes, nada sai da máquina) ou "datajud" (API Pública do CNJ).
PROCESS_SOURCE: str = env("PROCESS_SOURCE", default="fake")
DATAJUD_URL: str = env("DATAJUD_URL", default="https://api-publica.datajud.cnj.jus.br")
# Chave pública divulgada pelo CNJ na wiki do DataJud. Fica só em env: o CNJ troca às vezes.
DATAJUD_API_KEY: str = env("DATAJUD_API_KEY", default="")
DATAJUD_TIMEOUT: float = env.float("DATAJUD_TIMEOUT", default=30.0)
# Cada processo ativo é consultado no máximo a cada N horas.
CASE_CHECK_INTERVAL_HOURS: int = env.int("CASE_CHECK_INTERVAL_HOURS", default=2)
CASE_CHECKS_PER_RUN: int = env.int("CASE_CHECKS_PER_RUN", default=300)
# Intervalo entre consultas agendadas no mesmo ciclo (o DataJud devolve 429 fácil).
CASE_CHECK_SPACING_SECONDS: int = env.int("CASE_CHECK_SPACING_SECONDS", default=3)
# Publicações do Diário (DJEN) por OAB: "djen" (API pública do CNJ, sem chave) ou "fake".
PUBLICATION_SOURCE: str = env("PUBLICATION_SOURCE", default="djen")
DJEN_URL: str = env("DJEN_URL", default="https://comunicaapi.pje.jus.br")
DJEN_TIMEOUT: float = env.float("DJEN_TIMEOUT", default=30.0)
# O DJEN aceita ~20 requisições por janela: uma OAB por vez, espaçadas.
PUBLICATION_CHECK_SPACING_SECONDS: int = env.int("PUBLICATION_CHECK_SPACING_SECONDS", default=10)
# Primeira busca de uma OAB recém-cadastrada olha esses dias para trás.
PUBLICATION_INITIAL_DAYS: int = env.int("PUBLICATION_INITIAL_DAYS", default=7)
# Andamento novo para nós, mas mais velho que isso, não vira aviso (reindexação da fonte).
MOVEMENT_NOTIFY_MAX_AGE_DAYS: int = env.int("MOVEMENT_NOTIFY_MAX_AGE_DAYS", default=30)

# Tabelas append-only: o role da aplicação perde UPDATE/DELETE e um trigger bloqueia
# alterações para qualquer role.
APPEND_ONLY_TABLES: list[str] = ["core_auditevent", "clientes_clienttermacceptance"]

# --------------------------------------------------------------------------- logging
# Regra: nunca logar conteúdo de mensagem, CPF, telefone ou payload de webhook.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}

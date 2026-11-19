"""Settings de teste.

O banco de teste é criado e migrado como tramitai_owner (DATABASE_OWNER_URL) e os testes rodam
como tramitai_app (DATABASE_URL). A troca de credenciais está em backend/conftest.py.
"""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-not-a-secret-just-long-enough-for-hs256")
os.environ.setdefault("DATABASE_URL", "postgres://tramitai_app:app-local@localhost:5432/tramitai")
os.environ.setdefault(
    "DATABASE_OWNER_URL", "postgres://tramitai_owner:owner-local@localhost:5432/tramitai"
)

from .base import *  # noqa: F403
from .base import env

DATABASE_OWNER = env.db("DATABASE_OWNER_URL")

REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {
        "login": "10000/min",
        "password_reset": "10000/min",
        "signup": "10000/min",
    },
}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

FIELD_ENCRYPTION_KEYS = ["dGVzdC1rZXktdGVzdC1rZXktdGVzdC1rZXktMTIzNDU="]
WHATSAPP_APP_SECRET = "test-app-secret"
WHATSAPP_VERIFY_TOKEN = "test-verify-token"
WHATSAPP_GATEWAY = "fake"
WHATSAPP_BAILEYS_GATEWAY = "fake"
WHATSAPP_BRIDGE_SECRET = "test-bridge-secret-with-at-least-32-chars"
WHATSAPP_BRIDGE_URL = "http://bridge.test"
LLM_PROVIDER = "fake"
MERCADOPAGO_CLIENT = "fake"
GOOGLE_CALENDAR_CLIENT = "fake"
PUBLIC_API_URL = "https://app.tramitai.test"
PROCESS_SOURCE = "fake"
PUBLICATION_SOURCE = "fake"
DJEN_PAGE_PAUSE_SECONDS = 0.0
DJEN_RATE_LIMIT_WAIT_SECONDS = 0.0
TRIAGE_DEBOUNCE_SECONDS = 0
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
FRONTEND_URL = "https://app.tramitai.test"

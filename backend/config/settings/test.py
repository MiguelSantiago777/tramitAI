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

REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {"login": "10000/min"}}  # noqa: F405
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

FIELD_ENCRYPTION_KEYS = ["dGVzdC1rZXktdGVzdC1rZXktdGVzdC1rZXktMTIzNDU="]
WHATSAPP_APP_SECRET = "test-app-secret"
WHATSAPP_VERIFY_TOKEN = "test-verify-token"
WHATSAPP_GATEWAY = "fake"
LLM_PROVIDER = "fake"
PROCESS_SOURCE = "fake"
TRIAGE_DEBOUNCE_SECONDS = 0

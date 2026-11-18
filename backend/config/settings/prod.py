from .base import *  # noqa: F403
from .base import env

DEBUG = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_HSTS_SECONDS = env.int("DJANGO_HSTS_SECONDS", default=60 * 60 * 24 * 30)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
# Chamadas internas chegam por HTTP direto no container (sem passar pelo Caddy): o
# healthcheck do Docker e os eventos da ponte do WhatsApp (assinados com HMAC).
SECURE_REDIRECT_EXEMPT = [r"^api/health/$", r"^api/webhooks/bridge/$"]

# Produção fala com o Mercado Pago de verdade, mesmo num .env antigo sem a variável.
MERCADOPAGO_CLIENT = env("MERCADOPAGO_CLIENT", default="http")

GOOGLE_CALENDAR_CLIENT = env("GOOGLE_CALENDAR_CLIENT", default="http")

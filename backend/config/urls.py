from django.contrib import admin
from django.db import transaction
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.agenda.api.google_views import GoogleCallbackView
from apps.cobranca.webhook import SubscriptionWebhookView
from apps.core.views import HealthView
from apps.financeiro.webhook import MercadoPagoWebhookView
from apps.whatsapp.webhook import BridgeWebhookView, WhatsAppWebhookView

handler404 = "apps.core.views.not_found"
handler500 = "apps.core.views.server_error"

api_v1 = [
    path("auth/", include("apps.accounts.api.urls")),
    path("tenant/", include("apps.tenants.api.urls")),
    path("", include("apps.clientes.api.urls")),
    path("", include("apps.processos.api.urls")),
    path("", include("apps.whatsapp.api.urls")),
    path("", include("apps.aprovacoes.api.urls")),
    path("", include("apps.agenda.api.urls")),
    path("", include("apps.funil.api.urls")),
    path("", include("apps.documentos.api.urls")),
    path("", include("apps.financeiro.api.urls")),
    path("", include("apps.cobranca.api.urls")),
    path("", include("apps.relatorios.api.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    # Fora do ATOMIC_REQUESTS: com o banco fora, a view ainda responde 503 em vez de 500.
    path("api/health/", transaction.non_atomic_requests(HealthView.as_view()), name="health"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/v1/", include(api_v1)),
    path("api/webhooks/whatsapp/", WhatsAppWebhookView.as_view(), name="whatsapp-webhook"),
    path("api/webhooks/bridge/", BridgeWebhookView.as_view(), name="bridge-webhook"),
    path(
        "api/oauth/google/callback/",
        transaction.non_atomic_requests(GoogleCallbackView.as_view()),
        name="google-oauth-callback",
    ),
    path(
        "api/webhooks/mercadopago-assinatura/",
        SubscriptionWebhookView.as_view(),
        name="mercadopago-subscription-webhook",
    ),
    path(
        "api/webhooks/mercadopago/<str:token>/",
        MercadoPagoWebhookView.as_view(),
        name="mercadopago-webhook",
    ),
]

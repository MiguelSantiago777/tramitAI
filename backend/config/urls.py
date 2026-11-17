from django.contrib import admin
from django.db import transaction
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core.views import HealthView

handler404 = "apps.core.views.not_found"
handler500 = "apps.core.views.server_error"

api_v1 = [
    path("auth/", include("apps.accounts.api.urls")),
    path("tenant/", include("apps.tenants.api.urls")),
    path("", include("apps.clientes.api.urls")),
    path("", include("apps.processos.api.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    # Fora do ATOMIC_REQUESTS: com o banco fora, a view ainda responde 503 em vez de 500.
    path("api/health/", transaction.non_atomic_requests(HealthView.as_view()), name="health"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/v1/", include(api_v1)),
]

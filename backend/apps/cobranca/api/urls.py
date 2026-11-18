from django.db import transaction
from django.urls import path
from rest_framework.routers import SimpleRouter

from .platform_views import (
    OfficeActionView,
    OfficeDetailView,
    OfficesView,
    OverviewView,
    PaymentLinkView,
    PaymentsView,
    PlanViewSet,
)
from .views import BillingRefreshView, BillingView, PlansView, SignupView

router = SimpleRouter()
router.register("platform/plans", PlanViewSet, basename="platform-plan")

urlpatterns = [
    path("auth/signup/", SignupView.as_view(), name="auth-signup"),
    path("billing/plans/", PlansView.as_view(), name="billing-plans"),
    # Falam com o Mercado Pago: fora da transação do request (ATOMIC_REQUESTS).
    path("billing/", transaction.non_atomic_requests(BillingView.as_view()), name="billing"),
    path(
        "billing/refresh/",
        transaction.non_atomic_requests(BillingRefreshView.as_view()),
        name="billing-refresh",
    ),
    # Painel da plataforma (só superusuário).
    path("platform/overview/", OverviewView.as_view(), name="platform-overview"),
    path("platform/offices/", OfficesView.as_view(), name="platform-offices"),
    path(
        "platform/offices/<uuid:office_id>/",
        OfficeDetailView.as_view(),
        name="platform-office",
    ),
    path(
        "platform/offices/<uuid:office_id>/payment-link/",
        transaction.non_atomic_requests(PaymentLinkView.as_view()),
        name="platform-office-payment-link",
    ),
    path(
        "platform/offices/<uuid:office_id>/<str:action>/",
        OfficeActionView.as_view(),
        name="platform-office-action",
    ),
    path("platform/payments/", PaymentsView.as_view(), name="platform-payments"),
    *router.urls,
]

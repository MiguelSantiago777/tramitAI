from django.db import transaction
from django.urls import path

from .views import BillingRefreshView, BillingView, PlansView, SignupView

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
]

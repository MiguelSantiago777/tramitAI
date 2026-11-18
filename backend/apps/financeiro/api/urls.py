from django.db import transaction
from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    FeeAgreementViewSet,
    InstallmentChargeView,
    InstallmentViewSet,
    MercadoPagoAccountView,
)

router = SimpleRouter()
router.register("fee-agreements", FeeAgreementViewSet, basename="fee-agreement")
router.register("installments", InstallmentViewSet, basename="installment")

urlpatterns = [
    # Falam com o Mercado Pago por HTTP: fora da transação do request (ATOMIC_REQUESTS).
    path(
        "installments/<str:pk>/charge/",
        transaction.non_atomic_requests(InstallmentChargeView.as_view()),
        name="installment-charge",
    ),
    path(
        "finance/mercadopago/",
        transaction.non_atomic_requests(MercadoPagoAccountView.as_view()),
        name="finance-mercadopago",
    ),
    *router.urls,
]

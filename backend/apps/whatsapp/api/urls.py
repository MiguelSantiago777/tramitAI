from django.db import transaction
from django.urls import path
from rest_framework.routers import SimpleRouter

from .connection import WhatsAppConnectionView
from .views import ConversationViewSet, QuickReplyViewSet

router = SimpleRouter()
router.register("conversations", ConversationViewSet, basename="conversation")
router.register("quick-replies", QuickReplyViewSet, basename="quick-reply")

urlpatterns = [
    # Fala com a ponte por HTTP: fora da transação do request (ATOMIC_REQUESTS).
    path(
        "whatsapp/connection/",
        transaction.non_atomic_requests(WhatsAppConnectionView.as_view()),
        name="whatsapp-connection",
    ),
    *router.urls,
]

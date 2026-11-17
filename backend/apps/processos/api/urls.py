from rest_framework.routers import SimpleRouter

from .views import LegalCaseViewSet

router = SimpleRouter()
router.register("cases", LegalCaseViewSet, basename="case")

urlpatterns = router.urls

from rest_framework.routers import SimpleRouter

from .publication_views import MonitoredOabViewSet, PublicationViewSet
from .views import LegalCaseViewSet

router = SimpleRouter()
router.register("cases", LegalCaseViewSet, basename="case")
router.register("monitored-oabs", MonitoredOabViewSet, basename="monitored-oab")
router.register("publications", PublicationViewSet, basename="publication")

urlpatterns = router.urls

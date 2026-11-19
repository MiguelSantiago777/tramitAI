from rest_framework.routers import SimpleRouter

from .draft_views import DocumentDraftViewSet
from .views import DocumentViewSet

router = SimpleRouter()
router.register("documents", DocumentViewSet, basename="document")
router.register("document-drafts", DocumentDraftViewSet, basename="document-draft")

urlpatterns = router.urls

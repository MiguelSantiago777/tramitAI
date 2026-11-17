from rest_framework.routers import SimpleRouter

from .views import DraftViewSet

router = SimpleRouter()
router.register("drafts", DraftViewSet, basename="draft")

urlpatterns = router.urls

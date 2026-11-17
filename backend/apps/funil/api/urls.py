from rest_framework.routers import SimpleRouter

from .views import OpportunityViewSet

router = SimpleRouter()
router.register("opportunities", OpportunityViewSet, basename="opportunity")

urlpatterns = router.urls

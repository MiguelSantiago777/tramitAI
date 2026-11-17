from rest_framework.routers import SimpleRouter

from .views import ClientViewSet, TagViewSet

router = SimpleRouter()
router.register("clients", ClientViewSet, basename="client")
router.register("tags", TagViewSet, basename="tag")

urlpatterns = router.urls

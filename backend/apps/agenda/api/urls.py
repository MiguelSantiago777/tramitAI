from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import EventViewSet, MyDeskView, TaskViewSet

router = SimpleRouter()
router.register("tasks", TaskViewSet, basename="task")
router.register("events", EventViewSet, basename="event")

urlpatterns = [
    path("my-desk/", MyDeskView.as_view(), name="my-desk"),
    *router.urls,
]

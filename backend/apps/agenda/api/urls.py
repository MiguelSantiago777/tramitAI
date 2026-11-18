from django.db import transaction
from django.urls import path
from rest_framework.routers import SimpleRouter

from .google_views import GoogleCalendarView
from .views import EventViewSet, MyDeskView, TaskViewSet

router = SimpleRouter()
router.register("tasks", TaskViewSet, basename="task")
router.register("events", EventViewSet, basename="event")

urlpatterns = [
    path("my-desk/", MyDeskView.as_view(), name="my-desk"),
    # Fala com o Google por HTTP: fora da transação do request.
    path(
        "agenda/google/",
        transaction.non_atomic_requests(GoogleCalendarView.as_view()),
        name="agenda-google",
    ),
    *router.urls,
]

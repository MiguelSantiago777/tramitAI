from django.urls import path

from .dashboard import DashboardView
from .views import (
    ClientTermVersionsView,
    ClientTermView,
    MembersView,
    TeamMemberView,
    TeamResendInviteView,
    TeamView,
    TenantSettingsView,
)

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="tenant-dashboard"),
    path("settings/", TenantSettingsView.as_view(), name="tenant-settings"),
    path("members/", MembersView.as_view(), name="tenant-members"),
    path("team/", TeamView.as_view(), name="tenant-team"),
    path("team/<uuid:membership_id>/", TeamMemberView.as_view(), name="tenant-team-member"),
    path(
        "team/<uuid:membership_id>/resend-invite/",
        TeamResendInviteView.as_view(),
        name="tenant-team-resend",
    ),
    path("term/", ClientTermView.as_view(), name="tenant-term"),
    path("term/versions/", ClientTermVersionsView.as_view(), name="tenant-term-versions"),
]

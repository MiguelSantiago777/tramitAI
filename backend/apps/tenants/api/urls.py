from django.urls import path

from .views import ClientTermVersionsView, ClientTermView, MembersView, TenantSettingsView

urlpatterns = [
    path("settings/", TenantSettingsView.as_view(), name="tenant-settings"),
    path("members/", MembersView.as_view(), name="tenant-members"),
    path("term/", ClientTermView.as_view(), name="tenant-term"),
    path("term/versions/", ClientTermVersionsView.as_view(), name="tenant-term-versions"),
]

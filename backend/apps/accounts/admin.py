from django.contrib import admin

from .models import Membership, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ["email", "full_name", "is_active", "is_staff"]
    search_fields = ["email", "full_name"]
    exclude = ["password", "user_permissions", "groups"]
    readonly_fields = ["last_login", "date_joined"]


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "tenant", "role", "is_active"]
    list_filter = ["role", "is_active"]
    autocomplete_fields = ["user", "tenant"]

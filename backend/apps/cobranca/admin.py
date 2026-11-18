from django.contrib import admin

from .models import Plan, Subscription


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "price", "max_users", "is_active", "sort"]
    list_editable = ["price", "is_active", "sort"]


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ["tenant", "status", "plan", "trial_ends_at", "paid_until", "mp_status"]
    list_filter = ["status", "plan"]
    search_fields = ["tenant__name", "payer_email", "mp_preapproval_id"]
    readonly_fields = [
        "mp_preapproval_id",
        "mp_status",
        "mp_init_point",
        "created_at",
        "updated_at",
    ]
    fields = [
        "tenant",
        "plan",
        "status",
        "trial_ends_at",
        "paid_until",
        "payer_email",
        "notes",
        "mp_preapproval_id",
        "mp_status",
        "mp_init_point",
        "created_at",
        "updated_at",
    ]

import uuid

from django.db.models import QuerySet

from apps.tenants.models import Tenant

from .models import Membership


def active_memberships(*, user_id: uuid.UUID) -> QuerySet[Membership]:
    return (
        Membership.objects.select_related("tenant")
        .filter(user_id=user_id, is_active=True, tenant__status=Tenant.Status.ACTIVE)
        .order_by("tenant__name")
    )


def active_membership(*, user_id: uuid.UUID, tenant_id: uuid.UUID) -> Membership | None:
    return active_memberships(user_id=user_id).filter(tenant_id=tenant_id).first()


def tenant_members(*, tenant_id: uuid.UUID) -> QuerySet[Membership]:
    """Membros ativos do escritório. Membership não tem RLS: o filtro por tenant é explícito."""
    return (
        Membership.objects.select_related("user")
        .filter(tenant_id=tenant_id, is_active=True, user__is_active=True)
        .order_by("user__full_name", "user__email")
    )

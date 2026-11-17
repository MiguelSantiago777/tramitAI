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

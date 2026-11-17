from dataclasses import dataclass

from django.db import transaction
from django.utils.text import slugify

from apps.accounts.models import Membership, User
from apps.core.tenancy import tenant_context

from .models import Tenant, TenantSettings


@dataclass(frozen=True)
class CreatedTenant:
    tenant: Tenant
    owner: User
    membership: Membership


@transaction.atomic
def create_tenant(
    *,
    name: str,
    owner_email: str,
    owner_password: str | None,
    owner_full_name: str = "",
    slug: str | None = None,
) -> CreatedTenant:
    """Onboarding de um escritório: tenant, configurações e o usuário OWNER.

    Se o e-mail já existe, reaproveita o usuário (ele passa a ter mais uma Membership).
    """
    tenant = Tenant.objects.create(name=name, slug=slug or slugify(name)[:60])

    owner = User.objects.filter(email__iexact=owner_email).first()
    if owner is None:
        owner = User.objects.create_user(
            email=owner_email, password=owner_password, full_name=owner_full_name
        )
    membership = Membership.objects.create(user=owner, tenant=tenant, role=Membership.Role.OWNER)

    with tenant_context(tenant.id):
        TenantSettings.objects.create()

    return CreatedTenant(tenant=tenant, owner=owner, membership=membership)

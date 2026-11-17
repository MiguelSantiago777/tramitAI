from dataclasses import dataclass
from pathlib import Path

from django.db import transaction
from django.utils.text import slugify

from apps.accounts.models import Membership, User
from apps.core.tenancy import tenant_context

from .models import ClientTermVersion, Tenant, TenantSettings

DEFAULT_TERM_PATH = Path(__file__).parent / "defaults" / "termo_ciencia_ia_v1.md"


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
        default_term = DEFAULT_TERM_PATH.read_text(encoding="utf-8")
        publish_term_version(body=default_term.replace("{{escritorio}}", tenant.name))

    return CreatedTenant(tenant=tenant, owner=owner, membership=membership)


def active_term_version() -> ClientTermVersion | None:
    return ClientTermVersion.objects.filter(is_active=True).first()


@transaction.atomic
def publish_term_version(*, body: str, created_by: User | None = None) -> ClientTermVersion:
    """Publica uma nova versão do termo e desativa a anterior. Versões antigas ficam intactas."""
    current = ClientTermVersion.objects.select_for_update().filter(is_active=True).first()
    last = ClientTermVersion.objects.order_by("-version").values_list("version", flat=True).first()
    if current is not None:
        current.is_active = False
        current.save(update_fields=["is_active", "updated_at"])
    return ClientTermVersion.objects.create(
        version=(last or 0) + 1, body=body.strip(), is_active=True, created_by=created_by
    )

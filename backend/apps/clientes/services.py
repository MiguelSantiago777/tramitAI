from datetime import datetime
from typing import Any

from django.utils import timezone
from rest_framework import status

from apps.accounts.models import User
from apps.core.exceptions import ApiError
from apps.tenants.services import active_term_version

from .models import Client, ClientTag, ClientTermAcceptance, Tag


def create_client(*, tags: list[Tag] | None = None, **data: Any) -> Client:
    client = Client.objects.create(**data)
    if tags:
        set_tags(client, tags)
    return client


def update_client(client: Client, *, tags: list[Tag] | None = None, **data: Any) -> Client:
    """`tags=None` mantém as etiquetas; lista (mesmo vazia) substitui."""
    for field, value in data.items():
        setattr(client, field, value)
    client.save()
    if tags is not None:
        set_tags(client, tags)
    return client


def set_tags(client: Client, tags: list[Tag]) -> None:
    wanted = {t.pk for t in tags}
    ClientTag.objects.filter(client=client).exclude(tag_id__in=wanted).delete()
    existing = set(ClientTag.objects.filter(client=client).values_list("tag_id", flat=True))
    ClientTag.objects.bulk_create(
        [
            ClientTag(tenant_id=client.tenant_id, client=client, tag=t)
            for t in tags
            if t.pk not in existing
        ]
    )


def register_term_acceptance(
    *,
    client: Client,
    channel: str,
    accepted_at: datetime | None = None,
    evidence: str = "",
    recorded_by: User | None = None,
) -> ClientTermAcceptance:
    """Registra o aceite da versão vigente do termo. O registro é append-only."""
    term = active_term_version()
    if term is None:
        raise ApiError(
            "O escritório ainda não publicou o termo de ciência.",
            code="no_active_term",
            status_code=status.HTTP_409_CONFLICT,
        )
    return ClientTermAcceptance.objects.create(
        client=client,
        term_version=term,
        channel=channel,
        accepted_at=accepted_at or timezone.now(),
        evidence=evidence,
        recorded_by=recorded_by,
    )

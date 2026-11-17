from datetime import datetime
from typing import Any

from django.utils import timezone
from rest_framework import status

from apps.accounts.models import User
from apps.core.exceptions import ApiError
from apps.tenants.services import active_term_version

from .models import Client, ClientTermAcceptance


def create_client(**data: Any) -> Client:
    return Client.objects.create(**data)


def update_client(client: Client, **data: Any) -> Client:
    for field, value in data.items():
        setattr(client, field, value)
    client.save()
    return client


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

"""Registro de auditoria. Use sempre `record()`; nunca grave conteúdo de mensagem em `data`."""

import uuid
from typing import Any

from django.db import models

from .models import AuditEvent

Actor = AuditEvent.ActorType


def record(
    action: str,
    entity: models.Model,
    *,
    actor_type: str,
    actor_user: Any = None,
    data: dict[str, Any] | None = None,
) -> AuditEvent:
    entity_id = entity.pk
    if not isinstance(entity_id, uuid.UUID):
        raise TypeError("Auditoria exige entidade com id UUID.")
    return AuditEvent.objects.create(
        actor_type=actor_type,
        actor_user=actor_user,
        action=action,
        entity_type=entity._meta.label_lower,
        entity_id=entity_id,
        data=data or {},
    )


def history(entity: models.Model) -> models.QuerySet[AuditEvent]:
    return AuditEvent.objects.filter(
        entity_type=entity._meta.label_lower, entity_id=entity.pk
    ).select_related("actor_user")

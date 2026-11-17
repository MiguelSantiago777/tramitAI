from typing import Any

from django.db import models


def schema_safe_queryset(view: Any, model: type[models.Model]) -> models.QuerySet[Any] | None:
    """Queryset vazio para o drf-spectacular gerar o schema sem tenant ativo.

    Retorna None em requests normais (aí a view monta o queryset de verdade).
    """
    if getattr(view, "swagger_fake_view", False):
        return model.unscoped.none()  # type: ignore[attr-defined]
    return None

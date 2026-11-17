from typing import Any

from django.db import models
from rest_framework import serializers


class TenantScopedPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    """FK de entrada que só aceita ids do tenant ativo.

    O queryset é montado na hora da validação (o manager de tenant exige contexto ativo,
    então não dá para passar `queryset=Model.objects.all()` na definição da classe).
    Importante: o FK do Postgres NÃO respeita RLS, então essa checagem é obrigatória.
    """

    def __init__(self, model: type[models.Model], **kwargs: Any) -> None:
        self.model = model
        kwargs.setdefault("pk_field", serializers.UUIDField())
        super().__init__(**kwargs)

    def get_queryset(self) -> models.QuerySet[Any]:
        return self.model.objects.all()  # type: ignore[attr-defined]

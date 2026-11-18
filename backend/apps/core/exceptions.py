"""Formato padrão de erro da API:

    {"error": {"code": "not_found", "message": "Não encontrado.", "details": {...}}}

`details` só aparece quando há algo útil (ex.: erros de validação por campo).
"""

from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.db import IntegrityError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler


class ApiError(exceptions.APIException):
    """Erro de domínio com código estável para o frontend tratar."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    default_code = "error"
    default_detail = "Requisição inválida."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail=message or self.default_detail, code=code or self.default_code)
        if status_code is not None:
            self.status_code = status_code
        self.error_code = code or self.default_code
        self.details = details


class SubscriptionRequired(ApiError):
    """Teste grátis ou assinatura vencidos: o frontend leva para a página de assinatura."""

    def __init__(self) -> None:
        super().__init__(
            "A assinatura do escritório venceu. Regularize para continuar usando.",
            code="subscription_required",
            status_code=402,
        )


def error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if details:
        body["details"] = details
    return {"error": body}


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()
    elif isinstance(exc, IntegrityError):
        # Corrida que passou pela validação (ex.: dois cadastros simultâneos do mesmo CPF).
        exc = ApiError("Conflito com um registro existente.", code="conflict", status_code=409)

    response = exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, ApiError):
        response.data = error_body(exc.error_code, str(exc.detail), exc.details)
    elif isinstance(exc, exceptions.ValidationError):
        response.data = error_body("validation_error", "Dados inválidos.", exc.detail)
    elif isinstance(exc, exceptions.APIException):
        codes = exc.get_codes()
        code = codes if isinstance(codes, str) else exc.default_code
        response.data = error_body(code, str(exc.detail))
    return response

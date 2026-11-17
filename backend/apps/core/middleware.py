from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from .tenancy import clear_tenant


class TenantContextMiddleware:
    """Garante que o ContextVar de tenant começa e termina vazio em cada request.

    Quem ativa o tenant é a autenticação JWT (apps.accounts.authentication).
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        clear_tenant()
        try:
            return self.get_response(request)
        finally:
            clear_tenant()

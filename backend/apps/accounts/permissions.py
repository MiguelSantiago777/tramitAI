from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from .authentication import get_membership
from .models import Membership


class IsTenantOwner(BasePermission):
    message = "Só o titular do escritório pode fazer isso."

    def has_permission(self, request: Request, view: Any) -> bool:
        return get_membership(request).role == Membership.Role.OWNER


class IsOwnerForWrites(IsTenantOwner):
    """Leitura para todos do escritório; escrita só para o titular."""

    def has_permission(self, request: Request, view: Any) -> bool:
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return super().has_permission(request, view)

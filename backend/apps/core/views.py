import logging

import redis
from django.conf import settings
from django.db import connection
from django.http import HttpRequest, JsonResponse
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .exceptions import error_body

logger = logging.getLogger(__name__)


class HealthView(APIView):
    """Readiness: confere Postgres e Redis. Sem autenticação."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        responses={
            200: inline_serializer(
                "Health",
                {
                    "status": serializers.CharField(),
                    "database": serializers.BooleanField(),
                    "redis": serializers.BooleanField(),
                },
            )
        },
        tags=["health"],
    )
    def get(self, request: Request) -> Response:
        checks = {"database": _check_database(), "redis": _check_redis()}
        healthy = all(checks.values())
        return Response(
            {"status": "ok" if healthy else "degraded", **checks},
            status=200 if healthy else 503,
        )


def _check_database() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return True
    except Exception:
        logger.exception("health: banco indisponível")
        return False


def _check_redis() -> bool:
    try:
        client = redis.Redis.from_url(settings.CELERY_BROKER_URL, socket_timeout=1)
        return bool(client.ping())
    except Exception:
        logger.exception("health: redis indisponível")
        return False


def not_found(request: HttpRequest, exception: Exception) -> JsonResponse:
    return JsonResponse(error_body("not_found", "Não encontrado."), status=404)


def server_error(request: HttpRequest) -> JsonResponse:
    return JsonResponse(error_body("server_error", "Erro interno. Tente novamente."), status=500)

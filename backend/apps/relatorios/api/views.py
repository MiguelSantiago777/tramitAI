from datetime import date, timedelta
from typing import Any

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import get_membership
from apps.accounts.models import Membership
from apps.core.exceptions import ApiError
from apps.relatorios import services


class OverviewQuerySerializer(serializers.Serializer[Any]):
    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)


class MonthPointSerializer(serializers.Serializer[Any]):
    month = serializers.DateField()
    received = serializers.DecimalField(max_digits=14, decimal_places=2)
    expected = serializers.DecimalField(max_digits=14, decimal_places=2)


class OverviewSerializer(serializers.Serializer[Any]):
    start = serializers.DateField()
    end = serializers.DateField()
    clients = serializers.DictField(child=serializers.IntegerField())
    funnel = serializers.DictField()
    whatsapp = serializers.DictField(child=serializers.IntegerField())
    ai = serializers.DictField()
    cases = serializers.DictField(child=serializers.IntegerField())
    tasks = serializers.DictField(child=serializers.IntegerField())
    finance = serializers.DictField()
    finance_months = MonthPointSerializer(many=True)


class ReportsOverviewView(APIView):
    """Números do período (padrão: mês atual). Titular e advogados."""

    @extend_schema(
        parameters=[OverviewQuerySerializer], responses=OverviewSerializer, tags=["relatorios"]
    )
    def get(self, request: Request) -> Response:
        if get_membership(request).role == Membership.Role.STAFF:
            raise ApiError(
                "Relatórios são para titular e advogados.",
                code="permission_denied",
                status_code=403,
            )
        query = OverviewQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        today = timezone.localdate()
        start: date = query.validated_data.get("start") or today.replace(day=1)
        end: date = query.validated_data.get("end") or today
        if end < start:
            raise ApiError("A data final é antes da inicial.", code="invalid_range")
        if end - start > timedelta(days=services.MAX_DAYS):
            raise ApiError("Período máximo de um ano.", code="invalid_range")
        data = services.overview(start, end)
        return Response(OverviewSerializer(data.__dict__).data)

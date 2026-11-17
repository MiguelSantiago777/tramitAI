"""Painel da tela inicial: contadores do escritório e andamentos recentes (tenant ativo)."""

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class RecentMovementSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    case_id = serializers.UUIDField()
    case_number = serializers.CharField()
    name = serializers.CharField()
    occurred_at = serializers.DateTimeField()
    notification = serializers.CharField()


class DashboardSerializer(serializers.Serializer):
    pending_drafts = serializers.IntegerField()
    urgent_drafts = serializers.IntegerField()
    awaiting_drafts = serializers.IntegerField()
    sent_last_7_days = serializers.IntegerField()
    unread_conversations = serializers.IntegerField()
    open_conversations = serializers.IntegerField()
    active_cases = serializers.IntegerField()
    cases_with_news = serializers.IntegerField()
    active_clients = serializers.IntegerField()
    leads = serializers.IntegerField()
    recent_movements = RecentMovementSerializer(many=True)


class DashboardView(APIView):
    @extend_schema(responses=DashboardSerializer, tags=["tenant"])
    def get(self, request: Request) -> Response:
        from apps.aprovacoes.models import OutboundDraft
        from apps.clientes.models import Client
        from apps.processos.models import CaseMovement, LegalCase
        from apps.whatsapp.models import Conversation

        week_ago = timezone.now() - timedelta(days=7)
        drafts = OutboundDraft.objects.aggregate(
            pending=Count("id", filter=Q(status=OutboundDraft.Status.DRAFT)),
            urgent=Count("id", filter=Q(status=OutboundDraft.Status.DRAFT, urgency="high")),
            awaiting=Count("id", filter=Q(status=OutboundDraft.Status.AWAITING)),
            sent=Count("id", filter=Q(status=OutboundDraft.Status.SENT, decided_at__gte=week_ago)),
        )
        conversations = Conversation.objects.filter(status=Conversation.Status.OPEN).aggregate(
            open=Count("id"), unread=Count("id", filter=Q(unread_count__gt=0))
        )
        active_cases = LegalCase.objects.filter(status=LegalCase.Status.ACTIVE)
        clients = Client.objects.aggregate(
            active=Count("id", filter=Q(status=Client.Status.ACTIVE)),
            leads=Count("id", filter=Q(status=Client.Status.LEAD)),
        )
        recent = (
            CaseMovement.objects.exclude(notification=CaseMovement.Notification.BASELINE)
            .select_related("case")
            .order_by("-occurred_at")[:6]
        )
        data = {
            "pending_drafts": drafts["pending"],
            "urgent_drafts": drafts["urgent"],
            "awaiting_drafts": drafts["awaiting"],
            "sent_last_7_days": drafts["sent"],
            "unread_conversations": conversations["unread"],
            "open_conversations": conversations["open"],
            "active_cases": active_cases.count(),
            "cases_with_news": active_cases.filter(
                movements__notification=CaseMovement.Notification.PENDING
            )
            .distinct()
            .count(),
            "active_clients": clients["active"],
            "leads": clients["leads"],
            "recent_movements": [
                {
                    "id": m.pk,
                    "case_id": m.case_id,
                    "case_number": m.case.cnj_formatted,
                    "name": m.name,
                    "occurred_at": m.occurred_at,
                    "notification": m.notification,
                }
                for m in recent
            ],
        }
        return Response(DashboardSerializer(data).data)

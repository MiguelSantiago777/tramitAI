from typing import Any, cast

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from apps.accounts.models import User
from apps.core.exceptions import ApiError
from apps.core.views_base import schema_safe_queryset
from apps.whatsapp import selectors, services
from apps.whatsapp.models import Conversation, Message, QuickReply

from .serializers import (
    ConversationFilterSerializer,
    ConversationSerializer,
    MessageSerializer,
    QuickReplySerializer,
    SendMessageSerializer,
)


@extend_schema(tags=["whatsapp"])
class ConversationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Inbox do WhatsApp. PATCH altera cliente vinculado, situação e responsável."""

    serializer_class = ConversationSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self) -> QuerySet[Conversation]:
        fake = schema_safe_queryset(self, Conversation)
        if fake is not None:
            return fake
        if self.action == "list":
            filters = ConversationFilterSerializer(data=self.request.query_params)
            filters.is_valid(raise_exception=True)
            return selectors.search_conversations(
                **filters.validated_data, user=cast(User, self.request.user)
            )
        return selectors.conversations_with_preview()

    def perform_update(self, serializer: BaseSerializer[Conversation]) -> None:
        serializer.instance = services.update_conversation(
            cast(Conversation, serializer.instance),
            user=cast(User, self.request.user),
            changes=dict(serializer.validated_data),
        )

    @extend_schema(parameters=[ConversationFilterSerializer])
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().list(request, *args, **kwargs)

    @extend_schema(responses=MessageSerializer(many=True))
    @action(detail=True, methods=["get"])
    def messages(self, request: Request, pk: str | None = None) -> Response:
        """Mensagens da conversa, da mais recente para a mais antiga (paginado)."""
        conversation = self.get_object()
        page = self.paginate_queryset(selectors.thread(conversation))
        return self.get_paginated_response(MessageSerializer(page, many=True).data)

    @extend_schema(request=SendMessageSerializer, responses={201: MessageSerializer})
    @messages.mapping.post
    def send(self, request: Request, pk: str | None = None) -> Response:
        """Resposta manual do escritório (texto livre, dentro da janela de 24h)."""
        conversation = self.get_object()
        payload = SendMessageSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        message = services.send_text_reply(
            conversation=conversation,
            body=payload.validated_data["body"],
            user=cast(User, request.user),
        )
        return Response(MessageSerializer(message).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses={202: None})
    @action(detail=True, methods=["post"], url_path="retry-ai")
    def retry_ai(self, request: Request, pk: str | None = None) -> Response:
        """Pede para a Vera tentar de novo responder a última mensagem do contato."""
        from django.db import transaction

        from apps.ia.tasks import triage_message

        conversation = self.get_object()
        last = (
            conversation.messages.filter(direction=Message.Direction.INBOUND)
            .order_by("-created_at")
            .first()
        )
        if last is None:
            raise ApiError("O contato ainda não mandou mensagem.", code="no_inbound")
        Conversation.objects.filter(pk=conversation.pk).update(ai_failed_at=None)
        args = (str(conversation.tenant_id), str(conversation.pk), str(last.pk))
        transaction.on_commit(lambda: triage_message.delay(*args))
        return Response(status=status.HTTP_202_ACCEPTED)

    @extend_schema(request=None, responses={204: None})
    @action(detail=True, methods=["post"])
    def read(self, request: Request, pk: str | None = None) -> Response:
        services.mark_read(self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["whatsapp"])
class QuickReplyViewSet(viewsets.ModelViewSet):
    """Respostas prontas da equipe. Qualquer pessoa do escritório cria e edita."""

    serializer_class = QuickReplySerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[QuickReply]:
        fake = schema_safe_queryset(self, QuickReply)
        if fake is not None:
            return fake
        return QuickReply.objects.order_by("title")

    def perform_create(self, serializer: BaseSerializer[QuickReply]) -> None:
        serializer.save(created_by=self.request.user)

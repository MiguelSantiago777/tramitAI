from django.db.models import Count, OuterRef, Q, QuerySet, Subquery

from apps.accounts.models import User
from apps.core.br import only_digits

from .models import Conversation, Message


def conversations_with_preview() -> QuerySet[Conversation]:
    last = Message.objects.filter(conversation=OuterRef("pk")).order_by("-created_at")
    return Conversation.objects.select_related("client", "suggested_client", "assignee").annotate(
        pending_drafts=Count("drafts", filter=Q(drafts__status="DRAFT"), distinct=True),
        last_body=Subquery(last.values("body")[:1]),
        last_direction=Subquery(last.values("direction")[:1]),
        last_type=Subquery(last.values("type")[:1]),
        last_status=Subquery(last.values("status")[:1]),
    )


def search_conversations(
    *,
    q: str = "",
    status: str = "",
    unread: bool = False,
    assignee: str = "",
    user: User | None = None,
) -> QuerySet[Conversation]:
    qs = conversations_with_preview()
    if assignee == "me":
        qs = qs.filter(assignee=user)
    elif assignee == "none":
        qs = qs.filter(assignee__isnull=True)
    if status:
        qs = qs.filter(status=status)
    if unread:
        qs = qs.filter(unread_count__gt=0)
    q = q.strip()
    if q:
        condition = Q(contact_name__icontains=q) | Q(client__name__icontains=q)
        digits = only_digits(q)
        if len(digits) >= 4:
            condition |= Q(wa_id__contains=digits)
        qs = qs.filter(condition)
    return qs.order_by("-last_message_at", "-created_at")


def thread(conversation: Conversation) -> QuerySet[Message]:
    return conversation.messages.select_related("sent_by").order_by("-created_at")

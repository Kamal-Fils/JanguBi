from typing import Optional
from uuid import UUID

from django.db.models import Count, OuterRef, Q, QuerySet, Subquery

from apps.messaging.models import (
    Conversation,
    ConversationExport,
    Message,
    MessageBlock,
    Notification,
    PriestProfile,
)
from apps.users.models import BaseUser


def conversation_list(*, user: BaseUser) -> QuerySet[Conversation]:
    unread_subquery = (
        Message.objects.filter(
            conversation=OuterRef("pk"),
            read_at__isnull=True,
            deleted_at__isnull=True,
        )
        .exclude(sender=user)
        .values("conversation")
        .annotate(cnt=Count("id"))
        .values("cnt")
    )

    return (
        Conversation.objects.filter(Q(participant_a=user) | Q(participant_b=user))
        .annotate(unread_count=Subquery(unread_subquery))
        .select_related("participant_a", "participant_b")
        .order_by("-last_message_at")
    )


def conversation_get(
    *, conversation_id: UUID, user: BaseUser
) -> Optional[Conversation]:
    return (
        Conversation.objects.filter(pk=conversation_id)
        .filter(Q(participant_a=user) | Q(participant_b=user))
        .select_related("participant_a", "participant_b")
        .first()
    )


def message_list(
    *,
    conversation: Conversation,
    before_id: Optional[UUID] = None,
    limit: int = 30,
) -> QuerySet[Message]:
    qs = (
        Message.objects.filter(conversation=conversation)
        .select_related("sender", "reply_to")
        .prefetch_related("attachments__file", "reactions")
        .order_by("-created_at")
    )
    if before_id is not None:
        qs = qs.filter(id__lt=before_id)
    return qs[:limit]


def unread_count(*, conversation: Conversation, user: BaseUser) -> int:
    return (
        Message.objects.filter(
            conversation=conversation,
            read_at__isnull=True,
            deleted_at__isnull=True,
        )
        .exclude(sender=user)
        .count()
    )


def priest_list_available() -> QuerySet[PriestProfile]:
    return (
        PriestProfile.objects.filter(accepts_pastoral_chat=True)
        .select_related("user")
        .order_by("user__email")
    )


def block_list(*, user: BaseUser) -> QuerySet[MessageBlock]:
    return MessageBlock.objects.filter(blocker=user).select_related("blocked")


def export_list(*, conversation: Conversation) -> QuerySet[ConversationExport]:
    return ConversationExport.objects.filter(conversation=conversation).order_by(
        "-created_at"
    )


def notification_list(
    *, user: BaseUser, unread_only: bool = False
) -> QuerySet[Notification]:
    qs = Notification.objects.filter(user=user).order_by("-created_at")
    if unread_only:
        qs = qs.filter(is_read=False)
    return qs

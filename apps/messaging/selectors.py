from typing import Optional
from uuid import UUID

from django.db import models
from django.db.models import Count, OuterRef, Q, QuerySet, Subquery
from django.db.models.functions import Coalesce

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
        .annotate(
            unread_count=Coalesce(
                Subquery(unread_subquery),
                0,
                output_field=models.IntegerField(),
            )
        )
        .select_related(
            "participant_a",
            "participant_a__profile",
            "participant_b",
            "participant_b__profile",
        )
        .order_by(models.F("last_message_at").desc(nulls_last=True))
    )


def conversation_get(
    *, conversation_id: UUID, user: BaseUser
) -> Optional[Conversation]:
    return (
        Conversation.objects.filter(pk=conversation_id)
        .filter(Q(participant_a=user) | Q(participant_b=user))
        .select_related(
            "participant_a",
            "participant_a__profile",
            "participant_b",
            "participant_b__profile",
        )
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
        .select_related("sender", "sender__profile", "reply_to")
        .prefetch_related("attachments__file", "reactions")
        .order_by("-created_at")
    )
    if before_id is not None:
        try:
            pivot = Message.objects.get(id=before_id)
            qs = qs.filter(created_at__lt=pivot.created_at)
        except Message.DoesNotExist:
            pass
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


# ---------------------------------------------------------------------------
# ClergicalMessage selectors
# ---------------------------------------------------------------------------

def clerical_message_inbox(*, user: "BaseUser") -> "QuerySet":
    from apps.messaging.models import ClergicalMessage

    return ClergicalMessage.objects.filter(individual_recipient=user).select_related("sender").order_by("-created_at")


def clerical_message_sent(*, user: "BaseUser") -> "QuerySet":
    from apps.messaging.models import ClergicalMessage

    return ClergicalMessage.objects.filter(sender=user).select_related("individual_recipient").order_by("-created_at")

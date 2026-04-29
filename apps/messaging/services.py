from datetime import date, timedelta
from typing import Optional

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import ApplicationError
from apps.messaging.models import (
    Conversation,
    ConversationExport,
    Message,
    MessageBlock,
    MessageReaction,
    Notification,
    PriestProfile,
)
from apps.users.models import BaseUser


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalize_participants(a: BaseUser, b: BaseUser) -> tuple[BaseUser, BaseUser]:
    if str(a.id) < str(b.id):
        return a, b
    return b, a


def _check_not_blocked(sender: BaseUser, receiver: BaseUser) -> None:
    if MessageBlock.objects.filter(
        blocker__in=[sender, receiver],
        blocked__in=[sender, receiver],
    ).exists():
        raise ApplicationError("Échange bloqué entre ces deux utilisateurs.")


def _check_cgu(conversation: Conversation, user: BaseUser) -> None:
    if user.id == conversation.participant_a_id:
        if conversation.cgu_accepted_by_a is None:
            raise ApplicationError("Vous devez accepter les CGU de messagerie.")
    else:
        if conversation.cgu_accepted_by_b is None:
            raise ApplicationError("Vous devez accepter les CGU de messagerie.")


def _check_rate_limit(sender: BaseUser, conversation: Conversation) -> None:
    key = f"msg_rate:{conversation.id}:{sender.id}:{date.today()}"
    count = cache.get_or_set(key, 0, timeout=86400)
    if count >= settings.MESSAGING_RATE_LIMIT_PER_DAY:
        raise ApplicationError(
            f"Limite de {settings.MESSAGING_RATE_LIMIT_PER_DAY} messages par jour atteinte."
        )
    cache.incr(key)


def _fanout_ws(conversation: Conversation, event_type: str, payload: dict) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    async_to_sync(channel_layer.group_send)(
        f"conv_{conversation.id}",
        {"type": event_type, **payload},
    )


def _fanout_notification(user: BaseUser, event_type: str, payload: dict) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    async_to_sync(channel_layer.group_send)(
        f"user_{user.id}",
        {"type": "notification.push", "event_type": event_type, **payload},
    )


# ---------------------------------------------------------------------------
# PriestProfile
# ---------------------------------------------------------------------------


@transaction.atomic
def priest_profile_create(*, user: BaseUser, accepted_by: BaseUser) -> PriestProfile:
    if hasattr(user, "priest_profile"):
        raise ApplicationError("Cet utilisateur a déjà un profil prêtre.")
    profile = PriestProfile.objects.create(user=user)
    return profile


@transaction.atomic
def priest_profile_accept_cgu(*, priest_profile: PriestProfile) -> PriestProfile:
    if priest_profile.cgu_accepted_at is not None:
        raise ApplicationError("CGU déjà acceptées.")
    priest_profile.cgu_accepted_at = timezone.now()
    priest_profile.save(update_fields=["cgu_accepted_at", "updated_at"])
    return priest_profile


@transaction.atomic
def priest_profile_update(
    *,
    priest_profile: PriestProfile,
    accepts_pastoral_chat: Optional[bool] = None,
    ordination_year: Optional[int] = None,
    bio: Optional[str] = None,
) -> PriestProfile:
    if accepts_pastoral_chat is not None:
        priest_profile.accepts_pastoral_chat = accepts_pastoral_chat
    if ordination_year is not None:
        priest_profile.ordination_year = ordination_year
    if bio is not None:
        priest_profile.bio = bio
    priest_profile.save(
        update_fields=["accepts_pastoral_chat", "ordination_year", "bio", "updated_at"]
    )
    return priest_profile


# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------


@transaction.atomic
def conversation_get_or_create(
    *, fidele: BaseUser, priest: BaseUser
) -> tuple[Conversation, bool]:
    participant_a, participant_b = _normalize_participants(fidele, priest)
    conversation, created = Conversation.objects.get_or_create(
        participant_a=participant_a,
        participant_b=participant_b,
    )
    return conversation, created


@transaction.atomic
def conversation_accept_cgu(*, conversation: Conversation, user: BaseUser) -> Conversation:
    now = timezone.now()
    if user.id == conversation.participant_a_id:
        if conversation.cgu_accepted_by_a is not None:
            raise ApplicationError("CGU déjà acceptées.")
        conversation.cgu_accepted_by_a = now
        conversation.save(update_fields=["cgu_accepted_by_a", "updated_at"])
    else:
        if conversation.cgu_accepted_by_b is not None:
            raise ApplicationError("CGU déjà acceptées.")
        conversation.cgu_accepted_by_b = now
        conversation.save(update_fields=["cgu_accepted_by_b", "updated_at"])
    return conversation


@transaction.atomic
def conversation_archive(*, conversation: Conversation, user: BaseUser) -> Conversation:
    conversation.is_archived = True
    conversation.save(update_fields=["is_archived", "updated_at"])
    return conversation


@transaction.atomic
def conversation_delete(*, conversation: Conversation, user: BaseUser) -> Conversation:
    Message.objects.filter(conversation=conversation).update(
        content="",
        deleted_at=timezone.now(),
    )
    purge_at = timezone.now() + timedelta(days=30)
    conversation.scheduled_purge_at = purge_at
    conversation.save(update_fields=["scheduled_purge_at", "updated_at"])
    return conversation


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------


@transaction.atomic
def message_send(
    *,
    conversation: Conversation,
    sender: BaseUser,
    content: str,
    client_message_id: Optional[str] = None,
    reply_to: Optional[Message] = None,
) -> Message:
    receiver = (
        conversation.participant_b
        if sender.id == conversation.participant_a_id
        else conversation.participant_a
    )

    _check_not_blocked(sender, receiver)
    _check_cgu(conversation, sender)
    _check_rate_limit(sender, conversation)

    if client_message_id:
        existing = Message.objects.filter(client_message_id=client_message_id).first()
        if existing:
            return existing

    now = timezone.now()
    message = Message.objects.create(
        conversation=conversation,
        sender=sender,
        content=content,
        reply_to=reply_to,
        client_message_id=client_message_id,
    )

    purge_days = settings.MESSAGING_PURGE_DAYS
    Conversation.objects.filter(pk=conversation.pk).update(
        last_message_at=now,
        scheduled_purge_at=now + timedelta(days=purge_days),
    )

    transaction.on_commit(
        lambda: _fanout_ws(
            conversation,
            "conv_message",
            {
                "message_id": str(message.id),
                "sender_id": str(sender.id),
                "content": content,
                "created_at": now.isoformat(),
            },
        )
    )

    return message


@transaction.atomic
def message_mark_read(*, conversation: Conversation, reader: BaseUser) -> int:
    updated = (
        Message.objects.filter(
            conversation=conversation,
            read_at__isnull=True,
            deleted_at__isnull=True,
        )
        .exclude(sender=reader)
        .update(read_at=timezone.now())
    )

    if updated:
        transaction.on_commit(
            lambda: _fanout_ws(
                conversation,
                "conv_read",
                {"reader_id": str(reader.id)},
            )
        )

    return updated


@transaction.atomic
def message_delete(*, message: Message, user: BaseUser) -> Message:
    if message.sender_id != user.id:
        raise ApplicationError("Vous ne pouvez supprimer que vos propres messages.")
    if message.is_deleted:
        raise ApplicationError("Message déjà supprimé.")
    message.content = ""
    message.deleted_at = timezone.now()
    message.save(update_fields=["content", "deleted_at", "updated_at"])
    return message


@transaction.atomic
def message_react(*, message: Message, user: BaseUser, emoji: str) -> MessageReaction:
    reaction, _ = MessageReaction.objects.get_or_create(
        message=message,
        user=user,
        emoji=emoji,
    )
    return reaction


@transaction.atomic
def message_unreact(*, message: Message, user: BaseUser, emoji: str) -> None:
    MessageReaction.objects.filter(message=message, user=user, emoji=emoji).delete()


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------


@transaction.atomic
def block_user(*, blocker: BaseUser, blocked: BaseUser) -> MessageBlock:
    if blocker.id == blocked.id:
        raise ApplicationError("Impossible de se bloquer soi-même.")
    block, created = MessageBlock.objects.get_or_create(blocker=blocker, blocked=blocked)
    if not created:
        raise ApplicationError("Cet utilisateur est déjà bloqué.")
    return block


@transaction.atomic
def unblock_user(*, blocker: BaseUser, blocked: BaseUser) -> None:
    deleted, _ = MessageBlock.objects.filter(blocker=blocker, blocked=blocked).delete()
    if not deleted:
        raise ApplicationError("Aucun blocage trouvé.")


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


@transaction.atomic
def conversation_export_request(
    *, conversation: Conversation, user: BaseUser
) -> ConversationExport:
    export = ConversationExport.objects.create(
        conversation=conversation,
        requested_by=user,
    )

    def _launch_task():
        from apps.messaging.tasks import generate_conversation_export

        generate_conversation_export.delay(export.id)

    transaction.on_commit(_launch_task)
    return export


# ---------------------------------------------------------------------------
# Notifications (REQ-RT)
# ---------------------------------------------------------------------------


@transaction.atomic
def notification_send(
    *, user: BaseUser, event_type: str, payload: dict
) -> Notification:
    notification = Notification.objects.create(
        user=user,
        event_type=event_type,
        payload=payload,
    )

    transaction.on_commit(lambda: _fanout_notification(user, event_type, payload))

    return notification


@transaction.atomic
def notification_mark_read(*, notification: Notification, user: BaseUser) -> Notification:
    if notification.user_id != user.id:
        raise ApplicationError("Accès refusé.")
    if notification.is_read:
        return notification
    notification.is_read = True
    notification.read_at = timezone.now()
    notification.save(update_fields=["is_read", "read_at", "updated_at"])
    return notification

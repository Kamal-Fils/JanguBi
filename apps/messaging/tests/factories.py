"""
factory_boy factories for apps/messaging tests.

Encryption is transparent at the model level (EncryptedTextField.get_prep_value),
so plain strings assigned to `content` are encrypted on save and decrypted on read
without any special handling required in factories.
"""

import factory
from factory.django import DjangoModelFactory

from apps.messaging.models import (
    Conversation,
    Message,
    MessageBlock,
    MessageReaction,
    Notification,
    PriestProfile,
)
from apps.users.tests.factories import BaseUserFactory


class PriestProfileFactory(DjangoModelFactory):
    user = factory.SubFactory(BaseUserFactory)
    accepts_pastoral_chat = True
    bio = factory.Sequence(lambda n: f"Bio du pretre {n}")
    ordination_year = 2000

    class Meta:
        model = PriestProfile


class ConversationFactory(DjangoModelFactory):
    """
    Creates a Conversation between two distinct users.
    Enforces participant_a.id < participant_b.id (UUID string comparison) at creation time.
    """

    participant_a = factory.SubFactory(BaseUserFactory)
    participant_b = factory.SubFactory(BaseUserFactory)

    class Meta:
        model = Conversation

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        a = kwargs.pop("participant_a")
        b = kwargs.pop("participant_b")
        # Enforce canonical ordering required by the model constraint
        if str(a.id) <= str(b.id):
            pa, pb = a, b
        else:
            pa, pb = b, a
        return model_class.objects.create(participant_a=pa, participant_b=pb, **kwargs)


class MessageFactory(DjangoModelFactory):
    conversation = factory.SubFactory(ConversationFactory)
    sender = factory.LazyAttribute(lambda o: o.conversation.participant_a)
    # Plain string — EncryptedTextField handles encryption transparently
    content = factory.Sequence(lambda n: f"Message content {n}")
    content_type = Message.ContentType.TEXT

    class Meta:
        model = Message


class MessageBlockFactory(DjangoModelFactory):
    blocker = factory.SubFactory(BaseUserFactory)
    blocked = factory.SubFactory(BaseUserFactory)

    class Meta:
        model = MessageBlock


class MessageReactionFactory(DjangoModelFactory):
    message = factory.SubFactory(MessageFactory)
    user = factory.SubFactory(BaseUserFactory)
    emoji = "like"

    class Meta:
        model = MessageReaction


class NotificationFactory(DjangoModelFactory):
    user = factory.SubFactory(BaseUserFactory)
    event_type = "test.event"
    payload = factory.LazyFunction(dict)
    is_read = False

    class Meta:
        model = Notification

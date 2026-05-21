"""
API-layer tests for apps/messaging.

Coverage targets per endpoint:
- 200/201 success (authenticated, valid payload)
- 401 unauthenticated
- 400 invalid payload (where an input serializer exists)
- 403 forbidden (not a participant / wrong role / not the owner)
- 404 not found (where applicable)

WebSocket fanout and Celery task dispatch triggered via transaction.on_commit
are suppressed throughout so tests stay synchronous and network-free.

URL namespace: "messaging" (registered in apps/api/urls.py as
  path("messaging/", include(("apps.messaging.urls", "messaging"))))
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.users.tests.factories import BaseUserFactory, SuperAdminFactory

from .factories import (
    ConversationFactory,
    MessageBlockFactory,
    MessageFactory,
    MessageReactionFactory,
    NotificationFactory,
    PriestProfileFactory,
)

# ---------------------------------------------------------------------------
# Patch targets used throughout
# ---------------------------------------------------------------------------

_ON_COMMIT = "django.db.transaction.on_commit"
_FANOUT_WS = "apps.messaging.services._fanout_ws"
_FANOUT_NOTIF = "apps.messaging.services._fanout_notification"
_CACHE = "apps.messaging.services.cache"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def auth_client():
    """Authenticated APIClient for a plain fidele user."""
    client = APIClient()
    user = BaseUserFactory()
    client.force_authenticate(user=user)
    client._user = user
    return client


@pytest.fixture
def admin_client():
    """Authenticated APIClient for a super-admin user."""
    client = APIClient()
    user = SuperAdminFactory()
    client.force_authenticate(user=user)
    client._user = user
    return client


@pytest.fixture
def anon_client():
    """Unauthenticated APIClient."""
    return APIClient()


def _mock_cache(return_value=0):
    """Return a cache mock whose get_or_set returns the given value."""
    m = MagicMock()
    m.get_or_set.return_value = return_value
    return m


# ---------------------------------------------------------------------------
# PriestProfile — create  (POST /messaging/priest-profile/)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_priest_profile_create_returns_201_for_admin(admin_client):
    # Arrange
    target_user = BaseUserFactory()
    url = reverse("api:messaging:priest-profile-create")

    # Act
    response = admin_client.post(url, {"user_id": str(target_user.id)}, format="json")

    # Assert
    assert response.status_code == 201
    assert str(target_user.id) == response.data["user_id"]


@pytest.mark.django_db
def test_priest_profile_create_requires_authentication(anon_client):
    url = reverse("api:messaging:priest-profile-create")
    response = anon_client.post(url, {"user_id": "irrelevant"}, format="json")
    assert response.status_code == 401


@pytest.mark.django_db
def test_priest_profile_create_returns_403_for_non_admin(auth_client):
    # Arrange
    target_user = BaseUserFactory()
    url = reverse("api:messaging:priest-profile-create")

    # Act
    response = auth_client.post(url, {"user_id": str(target_user.id)}, format="json")

    # Assert
    assert response.status_code == 403


@pytest.mark.django_db
def test_priest_profile_create_returns_400_when_profile_already_exists(admin_client):
    # Arrange
    existing = PriestProfileFactory()
    url = reverse("api:messaging:priest-profile-create")

    # Act
    response = admin_client.post(
        url, {"user_id": str(existing.user_id)}, format="json"
    )

    # Assert
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# PriestProfile — accept CGU  (POST /messaging/priest-profile/cgu/)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_priest_profile_cgu_returns_200_for_priest_owner():
    # Arrange
    profile = PriestProfileFactory(cgu_accepted_at=None)
    client = APIClient()
    client.force_authenticate(user=profile.user)
    url = reverse("api:messaging:priest-profile-cgu")

    # Act
    response = client.post(url)

    # Assert
    assert response.status_code == 200
    assert response.data["cgu_accepted_at"] is not None


@pytest.mark.django_db
def test_priest_profile_cgu_requires_authentication(anon_client):
    url = reverse("api:messaging:priest-profile-cgu")
    response = anon_client.post(url)
    assert response.status_code == 401


@pytest.mark.django_db
def test_priest_profile_cgu_returns_403_for_user_without_profile(auth_client):
    url = reverse("api:messaging:priest-profile-cgu")
    response = auth_client.post(url)
    assert response.status_code == 403


@pytest.mark.django_db
def test_priest_profile_cgu_returns_400_when_already_accepted():
    # Arrange
    profile = PriestProfileFactory(cgu_accepted_at=timezone.now())
    client = APIClient()
    client.force_authenticate(user=profile.user)
    url = reverse("api:messaging:priest-profile-cgu")

    # Act
    response = client.post(url)

    # Assert
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# PriestProfile — update  (PATCH /messaging/priest-profile/me/)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_priest_profile_update_returns_200():
    # Arrange
    profile = PriestProfileFactory(bio="Old bio")
    client = APIClient()
    client.force_authenticate(user=profile.user)
    url = reverse("api:messaging:priest-profile-update")

    # Act
    response = client.patch(url, {"bio": "New bio"}, format="json")

    # Assert
    assert response.status_code == 200
    assert response.data["bio"] == "New bio"


@pytest.mark.django_db
def test_priest_profile_update_requires_authentication(anon_client):
    url = reverse("api:messaging:priest-profile-update")
    response = anon_client.patch(url, {"bio": "x"}, format="json")
    assert response.status_code == 401


@pytest.mark.django_db
def test_priest_profile_update_returns_403_for_user_without_profile(auth_client):
    url = reverse("api:messaging:priest-profile-update")
    response = auth_client.patch(url, {"bio": "x"}, format="json")
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Priest list  (GET /messaging/priests/)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_priest_list_returns_200(auth_client):
    # Arrange
    PriestProfileFactory(accepts_pastoral_chat=True)
    url = reverse("api:messaging:priest-list")

    # Act
    response = auth_client.get(url)

    # Assert
    assert response.status_code == 200
    assert len(response.data) >= 1


@pytest.mark.django_db
def test_priest_list_requires_authentication(anon_client):
    url = reverse("api:messaging:priest-list")
    response = anon_client.get(url)
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Conversation list  (GET /messaging/conversations/)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_conversation_list_returns_200_with_user_conversations(auth_client):
    # Arrange
    ConversationFactory(participant_a=auth_client._user)
    url = reverse("api:messaging:conversation-list")

    # Act
    response = auth_client.get(url)

    # Assert
    assert response.status_code == 200
    assert len(response.data) == 1


@pytest.mark.django_db
def test_conversation_list_requires_authentication(anon_client):
    url = reverse("api:messaging:conversation-list")
    response = anon_client.get(url)
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Conversation create  (POST /messaging/conversations/create/)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_conversation_create_returns_201(auth_client):
    # Arrange
    priest_user = BaseUserFactory()
    url = reverse("api:messaging:conversation-create")

    # Act
    response = auth_client.post(
        url, {"priest_user_id": str(priest_user.id)}, format="json"
    )

    # Assert
    assert response.status_code == 201


@pytest.mark.django_db
def test_conversation_create_requires_authentication(anon_client):
    url = reverse("api:messaging:conversation-create")
    response = anon_client.post(url, {"priest_user_id": "x"}, format="json")
    assert response.status_code == 401


@pytest.mark.django_db
def test_conversation_create_returns_400_on_invalid_payload(auth_client):
    # Arrange — priest_user_id is required
    url = reverse("api:messaging:conversation-create")

    # Act
    response = auth_client.post(url, {}, format="json")

    # Assert
    assert response.status_code == 400


@pytest.mark.django_db
def test_conversation_create_returns_404_when_priest_not_found(auth_client):
    url = reverse("api:messaging:conversation-create")
    response = auth_client.post(
        url, {"priest_user_id": str(uuid.uuid4())}, format="json"
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Conversation accept CGU  (POST /messaging/conversations/<id>/cgu/)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_conversation_cgu_returns_200():
    # Arrange
    conv = ConversationFactory(cgu_accepted_by_a=None)
    client = APIClient()
    client.force_authenticate(user=conv.participant_a)
    url = reverse("api:messaging:conversation-cgu", kwargs={"conversation_id": conv.id})

    # Act
    response = client.post(url)

    # Assert
    assert response.status_code == 200
    assert response.data["cgu_accepted_by_a"] is not None


@pytest.mark.django_db
def test_conversation_cgu_requires_authentication(anon_client):
    conv = ConversationFactory()
    url = reverse("api:messaging:conversation-cgu", kwargs={"conversation_id": conv.id})
    response = anon_client.post(url)
    assert response.status_code == 401


@pytest.mark.django_db
def test_conversation_cgu_returns_403_for_non_participant(auth_client):
    conv = ConversationFactory()
    url = reverse("api:messaging:conversation-cgu", kwargs={"conversation_id": conv.id})
    response = auth_client.post(url)
    assert response.status_code == 403


@pytest.mark.django_db
def test_conversation_cgu_returns_400_when_already_accepted():
    # Arrange
    conv = ConversationFactory(cgu_accepted_by_a=timezone.now())
    client = APIClient()
    client.force_authenticate(user=conv.participant_a)
    url = reverse("api:messaging:conversation-cgu", kwargs={"conversation_id": conv.id})

    # Act
    response = client.post(url)

    # Assert
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Conversation archive  (POST /messaging/conversations/<id>/archive/)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_conversation_archive_returns_200():
    # Arrange
    conv = ConversationFactory(is_archived=False)
    client = APIClient()
    client.force_authenticate(user=conv.participant_a)
    url = reverse(
        "api:messaging:conversation-archive", kwargs={"conversation_id": conv.id}
    )

    # Act
    response = client.post(url)

    # Assert
    assert response.status_code == 200
    assert response.data["is_archived"] is True


@pytest.mark.django_db
def test_conversation_archive_requires_authentication(anon_client):
    conv = ConversationFactory()
    url = reverse(
        "api:messaging:conversation-archive", kwargs={"conversation_id": conv.id}
    )
    response = anon_client.post(url)
    assert response.status_code == 401


@pytest.mark.django_db
def test_conversation_archive_returns_403_for_non_participant(auth_client):
    conv = ConversationFactory()
    url = reverse(
        "api:messaging:conversation-archive", kwargs={"conversation_id": conv.id}
    )
    response = auth_client.post(url)
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Conversation delete  (DELETE /messaging/conversations/<id>/)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_conversation_delete_returns_204():
    # Arrange
    conv = ConversationFactory()
    client = APIClient()
    client.force_authenticate(user=conv.participant_a)
    url = reverse(
        "api:messaging:conversation-delete", kwargs={"conversation_id": conv.id}
    )

    # Act
    with patch(_ON_COMMIT, lambda fn: None):
        response = client.delete(url)

    # Assert
    assert response.status_code == 204


@pytest.mark.django_db
def test_conversation_delete_requires_authentication(anon_client):
    conv = ConversationFactory()
    url = reverse(
        "api:messaging:conversation-delete", kwargs={"conversation_id": conv.id}
    )
    response = anon_client.delete(url)
    assert response.status_code == 401


@pytest.mark.django_db
def test_conversation_delete_returns_403_for_non_participant(auth_client):
    conv = ConversationFactory()
    url = reverse(
        "api:messaging:conversation-delete", kwargs={"conversation_id": conv.id}
    )
    response = auth_client.delete(url)
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Conversation export  (POST/GET /messaging/conversations/<id>/export/)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_conversation_export_post_returns_201():
    # Arrange
    conv = ConversationFactory()
    client = APIClient()
    client.force_authenticate(user=conv.participant_a)
    url = reverse(
        "api:messaging:conversation-export", kwargs={"conversation_id": conv.id}
    )

    # Act
    with patch(_ON_COMMIT, lambda fn: None):
        response = client.post(url)

    # Assert
    assert response.status_code == 201


@pytest.mark.django_db
def test_conversation_export_get_returns_200():
    # Arrange
    conv = ConversationFactory()
    client = APIClient()
    client.force_authenticate(user=conv.participant_a)
    url = reverse(
        "api:messaging:conversation-export", kwargs={"conversation_id": conv.id}
    )

    # Act
    response = client.get(url)

    # Assert
    assert response.status_code == 200


@pytest.mark.django_db
def test_conversation_export_requires_authentication(anon_client):
    conv = ConversationFactory()
    url = reverse(
        "api:messaging:conversation-export", kwargs={"conversation_id": conv.id}
    )
    response = anon_client.post(url)
    assert response.status_code == 401


@pytest.mark.django_db
def test_conversation_export_returns_403_for_non_participant(auth_client):
    conv = ConversationFactory()
    url = reverse(
        "api:messaging:conversation-export", kwargs={"conversation_id": conv.id}
    )
    response = auth_client.post(url)
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Message list  (GET /messaging/conversations/<id>/messages/)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_message_list_returns_200():
    # Arrange
    conv = ConversationFactory(
        cgu_accepted_by_a=timezone.now(), cgu_accepted_by_b=timezone.now()
    )
    client = APIClient()
    client.force_authenticate(user=conv.participant_a)
    MessageFactory(conversation=conv, sender=conv.participant_a)
    url = reverse("api:messaging:message-list", kwargs={"conversation_id": conv.id})

    # Act
    response = client.get(url)

    # Assert
    assert response.status_code == 200
    assert len(response.data) == 1


@pytest.mark.django_db
def test_message_list_requires_authentication(anon_client):
    conv = ConversationFactory()
    url = reverse("api:messaging:message-list", kwargs={"conversation_id": conv.id})
    response = anon_client.get(url)
    assert response.status_code == 401


@pytest.mark.django_db
def test_message_list_returns_403_for_non_participant(auth_client):
    conv = ConversationFactory(
        cgu_accepted_by_a=timezone.now(), cgu_accepted_by_b=timezone.now()
    )
    url = reverse("api:messaging:message-list", kwargs={"conversation_id": conv.id})
    response = auth_client.get(url)
    assert response.status_code == 403


@pytest.mark.django_db
def test_message_list_returns_403_when_cgu_not_accepted():
    # Arrange — participant_a has NOT accepted CGU
    conv = ConversationFactory(
        cgu_accepted_by_a=None, cgu_accepted_by_b=timezone.now()
    )
    client = APIClient()
    client.force_authenticate(user=conv.participant_a)
    url = reverse("api:messaging:message-list", kwargs={"conversation_id": conv.id})

    # Act
    response = client.get(url)

    # Assert
    assert response.status_code == 403


@pytest.mark.django_db
def test_message_list_respects_limit_query_param():
    # Arrange
    conv = ConversationFactory(
        cgu_accepted_by_a=timezone.now(), cgu_accepted_by_b=timezone.now()
    )
    client = APIClient()
    client.force_authenticate(user=conv.participant_a)
    for _ in range(10):
        MessageFactory(conversation=conv, sender=conv.participant_a)
    url = reverse("api:messaging:message-list", kwargs={"conversation_id": conv.id})

    # Act
    response = client.get(url, {"limit": 3})

    # Assert
    assert response.status_code == 200
    assert len(response.data) == 3


# ---------------------------------------------------------------------------
# Message send  (POST /messaging/conversations/<id>/messages/send/)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_message_send_returns_201():
    # Arrange
    conv = ConversationFactory(
        cgu_accepted_by_a=timezone.now(), cgu_accepted_by_b=timezone.now()
    )
    client = APIClient()
    client.force_authenticate(user=conv.participant_a)
    url = reverse("api:messaging:message-send", kwargs={"conversation_id": conv.id})

    # Act
    with patch(_CACHE, _mock_cache(0)):
        with patch(_ON_COMMIT, lambda fn: fn()):
            with patch(_FANOUT_WS):
                response = client.post(url, {"content": "Hello!"}, format="json")

    # Assert
    assert response.status_code == 201
    assert response.data["content"] == "Hello!"


@pytest.mark.django_db
def test_message_send_requires_authentication(anon_client):
    conv = ConversationFactory()
    url = reverse("api:messaging:message-send", kwargs={"conversation_id": conv.id})
    response = anon_client.post(url, {"content": "x"}, format="json")
    assert response.status_code == 401


@pytest.mark.django_db
def test_message_send_returns_400_on_empty_payload():
    # Arrange
    conv = ConversationFactory(
        cgu_accepted_by_a=timezone.now(), cgu_accepted_by_b=timezone.now()
    )
    client = APIClient()
    client.force_authenticate(user=conv.participant_a)
    url = reverse("api:messaging:message-send", kwargs={"conversation_id": conv.id})

    # Act
    response = client.post(url, {}, format="json")

    # Assert
    assert response.status_code == 400


@pytest.mark.django_db
def test_message_send_returns_403_for_non_participant(auth_client):
    conv = ConversationFactory(
        cgu_accepted_by_a=timezone.now(), cgu_accepted_by_b=timezone.now()
    )
    url = reverse("api:messaging:message-send", kwargs={"conversation_id": conv.id})
    response = auth_client.post(url, {"content": "Hi"}, format="json")
    assert response.status_code == 403


@pytest.mark.django_db
def test_message_send_returns_403_when_cgu_not_accepted():
    # Arrange — participant_a has NOT accepted CGU
    conv = ConversationFactory(
        cgu_accepted_by_a=None, cgu_accepted_by_b=timezone.now()
    )
    client = APIClient()
    client.force_authenticate(user=conv.participant_a)
    url = reverse("api:messaging:message-send", kwargs={"conversation_id": conv.id})

    # Act
    response = client.post(url, {"content": "Hi"}, format="json")

    # Assert
    assert response.status_code == 403


@pytest.mark.django_db
def test_message_send_returns_400_when_sender_blocked():
    # Arrange
    conv = ConversationFactory(
        cgu_accepted_by_a=timezone.now(), cgu_accepted_by_b=timezone.now()
    )
    sender = conv.participant_a
    receiver = conv.participant_b
    MessageBlockFactory(blocker=sender, blocked=receiver)
    client = APIClient()
    client.force_authenticate(user=sender)
    url = reverse("api:messaging:message-send", kwargs={"conversation_id": conv.id})

    # Act — block check fires before rate-limit; no cache mock needed
    with patch(_CACHE, _mock_cache(0)):
        response = client.post(url, {"content": "Hi"}, format="json")

    # Assert
    assert response.status_code == 400


@pytest.mark.django_db
def test_message_send_is_idempotent_with_same_client_message_id():
    # Arrange
    conv = ConversationFactory(
        cgu_accepted_by_a=timezone.now(), cgu_accepted_by_b=timezone.now()
    )
    client = APIClient()
    client.force_authenticate(user=conv.participant_a)
    url = reverse("api:messaging:message-send", kwargs={"conversation_id": conv.id})
    client_msg_id = str(uuid.uuid4())

    # Act — send twice with the same client_message_id
    with patch(_CACHE, _mock_cache(0)):
        with patch(_ON_COMMIT, lambda fn: fn()):
            with patch(_FANOUT_WS):
                r1 = client.post(
                    url,
                    {"content": "Hello", "client_message_id": client_msg_id},
                    format="json",
                )
                r2 = client.post(
                    url,
                    {"content": "Hello", "client_message_id": client_msg_id},
                    format="json",
                )

    # Assert — same message id returned both times
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.data["id"] == r2.data["id"]


# ---------------------------------------------------------------------------
# Message read  (POST /messaging/conversations/<id>/read/)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_message_read_returns_200():
    # Arrange
    conv = ConversationFactory()
    sender = conv.participant_a
    reader = conv.participant_b
    MessageFactory(conversation=conv, sender=sender, read_at=None)
    client = APIClient()
    client.force_authenticate(user=reader)
    url = reverse("api:messaging:message-read", kwargs={"conversation_id": conv.id})

    # Act
    with patch(_ON_COMMIT, lambda fn: fn()):
        with patch(_FANOUT_WS):
            response = client.post(url)

    # Assert
    assert response.status_code == 200
    assert response.data["status"] == "ok"


@pytest.mark.django_db
def test_message_read_requires_authentication(anon_client):
    conv = ConversationFactory()
    url = reverse("api:messaging:message-read", kwargs={"conversation_id": conv.id})
    response = anon_client.post(url)
    assert response.status_code == 401


@pytest.mark.django_db
def test_message_read_returns_403_for_non_participant(auth_client):
    conv = ConversationFactory()
    url = reverse("api:messaging:message-read", kwargs={"conversation_id": conv.id})
    response = auth_client.post(url)
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Message delete  (DELETE /messaging/messages/<id>/)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_message_delete_returns_204():
    # Arrange
    msg = MessageFactory()
    client = APIClient()
    client.force_authenticate(user=msg.sender)
    url = reverse("api:messaging:message-delete", kwargs={"message_id": msg.id})

    # Act
    response = client.delete(url)

    # Assert
    assert response.status_code == 204


@pytest.mark.django_db
def test_message_delete_requires_authentication(anon_client):
    msg = MessageFactory()
    url = reverse("api:messaging:message-delete", kwargs={"message_id": msg.id})
    response = anon_client.delete(url)
    assert response.status_code == 401


@pytest.mark.django_db
def test_message_delete_returns_403_for_non_sender(auth_client):
    # Arrange — auth_client._user is a different user from msg.sender
    msg = MessageFactory()
    url = reverse("api:messaging:message-delete", kwargs={"message_id": msg.id})

    # Act
    response = auth_client.delete(url)

    # Assert
    assert response.status_code == 403


@pytest.mark.django_db
def test_message_delete_returns_400_when_already_deleted():
    # Arrange
    msg = MessageFactory(deleted_at=timezone.now(), content="")
    client = APIClient()
    client.force_authenticate(user=msg.sender)
    url = reverse("api:messaging:message-delete", kwargs={"message_id": msg.id})

    # Act
    response = client.delete(url)

    # Assert
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Message react  (POST/DELETE /messaging/messages/<id>/react/)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_message_react_post_returns_201(auth_client):
    # Arrange — auth_client._user must be a participant in the conversation
    conv = ConversationFactory(participant_a=auth_client._user)
    msg = MessageFactory(conversation=conv, sender=conv.participant_a)
    url = reverse("api:messaging:message-react", kwargs={"message_id": msg.id})

    # Act
    response = auth_client.post(url, {"emoji": "like"}, format="json")

    # Assert
    assert response.status_code == 201


@pytest.mark.django_db
def test_message_react_post_returns_403_for_non_participant(auth_client):
    # Arrange — message belongs to a conversation auth_client._user is NOT in
    msg = MessageFactory()
    url = reverse("api:messaging:message-react", kwargs={"message_id": msg.id})

    # Act
    response = auth_client.post(url, {"emoji": "like"}, format="json")

    # Assert
    assert response.status_code == 403


@pytest.mark.django_db
def test_message_react_post_requires_authentication(anon_client):
    msg = MessageFactory()
    url = reverse("api:messaging:message-react", kwargs={"message_id": msg.id})
    response = anon_client.post(url, {"emoji": "like"}, format="json")
    assert response.status_code == 401


@pytest.mark.django_db
def test_message_react_post_returns_400_on_missing_emoji(auth_client):
    # Arrange — auth_client._user must be a participant so we reach input validation
    conv = ConversationFactory(participant_a=auth_client._user)
    msg = MessageFactory(conversation=conv, sender=conv.participant_a)
    url = reverse("api:messaging:message-react", kwargs={"message_id": msg.id})

    # Act
    response = auth_client.post(url, {}, format="json")

    # Assert
    assert response.status_code == 400


@pytest.mark.django_db
def test_message_react_delete_returns_204(auth_client):
    # Arrange — auth_client._user must be a participant in the reaction's conversation
    conv = ConversationFactory(participant_a=auth_client._user)
    msg = MessageFactory(conversation=conv, sender=conv.participant_a)
    reaction = MessageReactionFactory(message=msg, user=auth_client._user, emoji="love")
    url = reverse(
        "api:messaging:message-react", kwargs={"message_id": reaction.message.id}
    )

    # Act
    response = auth_client.delete(url, {"emoji": "love"}, format="json")

    # Assert
    assert response.status_code == 204


@pytest.mark.django_db
def test_message_react_delete_returns_403_for_non_participant(auth_client):
    # Arrange — message belongs to a conversation auth_client._user is NOT in
    reaction = MessageReactionFactory(emoji="love")
    url = reverse(
        "api:messaging:message-react", kwargs={"message_id": reaction.message.id}
    )

    # Act
    response = auth_client.delete(url, {"emoji": "love"}, format="json")

    # Assert
    assert response.status_code == 403


@pytest.mark.django_db
def test_message_react_delete_requires_authentication(anon_client):
    reaction = MessageReactionFactory(emoji="love")
    url = reverse(
        "api:messaging:message-react", kwargs={"message_id": reaction.message.id}
    )
    response = anon_client.delete(url, {"emoji": "love"}, format="json")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Block list + create  (GET/POST /messaging/blocks/)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_block_list_returns_200(auth_client):
    # Arrange
    target = BaseUserFactory()
    MessageBlockFactory(blocker=auth_client._user, blocked=target)
    url = reverse("api:messaging:block-list-create")

    # Act
    response = auth_client.get(url)

    # Assert
    assert response.status_code == 200
    assert len(response.data) == 1


@pytest.mark.django_db
def test_block_list_requires_authentication(anon_client):
    url = reverse("api:messaging:block-list-create")
    response = anon_client.get(url)
    assert response.status_code == 401


@pytest.mark.django_db
def test_block_create_returns_201(auth_client):
    # Arrange
    target = BaseUserFactory()
    url = reverse("api:messaging:block-list-create")

    # Act
    response = auth_client.post(
        url, {"blocked_user_id": str(target.id)}, format="json"
    )

    # Assert
    assert response.status_code == 201


@pytest.mark.django_db
def test_block_create_requires_authentication(anon_client):
    url = reverse("api:messaging:block-list-create")
    response = anon_client.post(url, {"blocked_user_id": "x"}, format="json")
    assert response.status_code == 401


@pytest.mark.django_db
def test_block_create_returns_400_on_missing_payload(auth_client):
    url = reverse("api:messaging:block-list-create")
    response = auth_client.post(url, {}, format="json")
    assert response.status_code == 400


@pytest.mark.django_db
def test_block_create_returns_400_when_user_already_blocked(auth_client):
    # Arrange
    target = BaseUserFactory()
    MessageBlockFactory(blocker=auth_client._user, blocked=target)
    url = reverse("api:messaging:block-list-create")

    # Act
    response = auth_client.post(
        url, {"blocked_user_id": str(target.id)}, format="json"
    )

    # Assert
    assert response.status_code == 400


@pytest.mark.django_db
def test_block_create_returns_400_when_blocking_self(auth_client):
    url = reverse("api:messaging:block-list-create")
    response = auth_client.post(
        url, {"blocked_user_id": str(auth_client._user.id)}, format="json"
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Block delete  (DELETE /messaging/blocks/<id>/)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_block_delete_returns_204(auth_client):
    # Arrange
    target = BaseUserFactory()
    block = MessageBlockFactory(blocker=auth_client._user, blocked=target)
    url = reverse("api:messaging:block-delete", kwargs={"block_id": block.id})

    # Act
    response = auth_client.delete(url)

    # Assert
    assert response.status_code == 204


@pytest.mark.django_db
def test_block_delete_requires_authentication(anon_client):
    block = MessageBlockFactory()
    url = reverse("api:messaging:block-delete", kwargs={"block_id": block.id})
    response = anon_client.delete(url)
    assert response.status_code == 401


@pytest.mark.django_db
def test_block_delete_returns_403_for_non_owner(auth_client):
    # Arrange — block is owned by a different user
    block = MessageBlockFactory()
    url = reverse("api:messaging:block-delete", kwargs={"block_id": block.id})

    # Act
    response = auth_client.delete(url)

    # Assert
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Notification list  (GET /messaging/notifications/)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_notification_list_returns_200(auth_client):
    # Arrange
    NotificationFactory(user=auth_client._user)
    url = reverse("api:messaging:notification-list")

    # Act
    response = auth_client.get(url)

    # Assert
    assert response.status_code == 200
    assert len(response.data) == 1


@pytest.mark.django_db
def test_notification_list_unread_only_query_param(auth_client):
    # Arrange
    NotificationFactory(user=auth_client._user, is_read=False)
    NotificationFactory(user=auth_client._user, is_read=True)
    url = reverse("api:messaging:notification-list")

    # Act
    response = auth_client.get(url, {"unread_only": "true"})

    # Assert
    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["is_read"] is False


@pytest.mark.django_db
def test_notification_list_requires_authentication(anon_client):
    url = reverse("api:messaging:notification-list")
    response = anon_client.get(url)
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Notification mark read  (POST /messaging/notifications/<id>/read/)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_notification_read_returns_200(auth_client):
    # Arrange
    notif = NotificationFactory(user=auth_client._user, is_read=False)
    url = reverse(
        "api:messaging:notification-read", kwargs={"notification_id": notif.id}
    )

    # Act
    response = auth_client.post(url)

    # Assert
    assert response.status_code == 200
    assert response.data["is_read"] is True


@pytest.mark.django_db
def test_notification_read_requires_authentication(anon_client):
    notif = NotificationFactory()
    url = reverse(
        "api:messaging:notification-read", kwargs={"notification_id": notif.id}
    )
    response = anon_client.post(url)
    assert response.status_code == 401


@pytest.mark.django_db
def test_notification_read_returns_400_for_wrong_user(auth_client):
    # Arrange — notification belongs to a different user
    notif = NotificationFactory(is_read=False)
    url = reverse(
        "api:messaging:notification-read", kwargs={"notification_id": notif.id}
    )

    # Act
    response = auth_client.post(url)

    # Assert
    assert response.status_code == 400


@pytest.mark.django_db
def test_notification_read_returns_404_when_not_found(auth_client):
    url = reverse(
        "api:messaging:notification-read",
        kwargs={"notification_id": uuid.uuid4()},
    )
    response = auth_client.post(url)
    assert response.status_code == 404

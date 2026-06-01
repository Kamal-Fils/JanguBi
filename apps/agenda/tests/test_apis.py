import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.agenda.models import Event
from apps.users.enums import UserOnboardingState
from apps.users.models import BaseUser

import datetime


def _make_user(email, pastoral_role="fidele", role="fidele"):
    user = BaseUser.objects.create_user(
        email=email,
        password="StrongPassw0rd!",
        role=role,
        phone_number=f"+221770{abs(hash(email)) % 1_000_000:06d}",
        is_active=True,
        is_verified=True,
    )
    user.pastoral_role = pastoral_role
    user.onboarding_state = UserOnboardingState.COMPLETED  # onboardé → peut écrire (A1)
    user.save(update_fields=["pastoral_role", "onboarding_state"])
    return user


def _event_data():
    now = timezone.now()
    return {
        "title": "Messe dominicale",
        "event_type": "mass",
        "start_at": (now + datetime.timedelta(hours=2)).isoformat(),
        "end_at": (now + datetime.timedelta(hours=3)).isoformat(),
        "scope_type": "global",
    }


@pytest.fixture
def pretre_client(db):
    client = APIClient()
    user = _make_user("pretre@example.com", "pretre")
    client.force_authenticate(user=user)
    client._user = user
    return client


@pytest.fixture
def fidele_client(db):
    client = APIClient()
    user = _make_user("fidele@example.com", "fidele")
    client.force_authenticate(user=user)
    client._user = user
    return client


@pytest.mark.django_db
def test_event_create_clergy_201(pretre_client):
    url = reverse("api:agenda:event-list-create")
    resp = pretre_client.post(url, _event_data(), format="json")
    assert resp.status_code == status.HTTP_201_CREATED
    assert Event.objects.filter(organizer=pretre_client._user).count() == 1


@pytest.mark.django_db
def test_event_create_fidele_400(fidele_client):
    url = reverse("api:agenda:event-list-create")
    resp = fidele_client.post(url, _event_data(), format="json")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_event_list(fidele_client, pretre_client):
    now = timezone.now()
    Event.objects.create(
        organizer=pretre_client._user,
        title="Test",
        event_type="mass",
        start_at=now + datetime.timedelta(hours=1),
        end_at=now + datetime.timedelta(hours=2),
        scope_type="global",
    )
    url = reverse("api:agenda:event-list-create")
    resp = fidele_client.get(url)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["count"] == 1


@pytest.mark.django_db
def test_event_register(fidele_client, pretre_client):
    now = timezone.now()
    event = Event.objects.create(
        organizer=pretre_client._user,
        title="Retraite",
        event_type="retreat",
        start_at=now + datetime.timedelta(days=1),
        end_at=now + datetime.timedelta(days=2),
        scope_type="global",
    )
    url = reverse("api:agenda:event-register", kwargs={"event_id": event.pk})
    resp = fidele_client.post(url)
    assert resp.status_code == status.HTTP_201_CREATED
    assert event.registrations.count() == 1


@pytest.mark.django_db
def test_event_register_full(fidele_client, pretre_client):
    now = timezone.now()
    event = Event.objects.create(
        organizer=pretre_client._user,
        title="Petite messe",
        event_type="mass",
        start_at=now + datetime.timedelta(hours=1),
        end_at=now + datetime.timedelta(hours=2),
        scope_type="global",
        max_participants=0,
    )
    url = reverse("api:agenda:event-register", kwargs={"event_id": event.pk})
    resp = fidele_client.post(url)
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_event_requires_auth():
    client = APIClient()
    url = reverse("api:agenda:event-list-create")
    resp = client.get(url)
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_event_register_pending_parish_blocked_returns_403():
    # EXPLOIT A1 : un fidèle pur en pending_parish (paroisse non choisie) ne peut
    # PAS s'inscrire à un événement. Même endpoint que test_event_register
    # (completed → 201) : seul l'onboarding_state change → le 403 vient de la garde.
    # La garde (has_permission) précède la résolution de l'objet, d'où l'event_id factice.
    user = BaseUser.objects.create_user(
        email="pending_ag@test.com",
        password="StrongPassw0rd!",
        role="fidele",
        phone_number="+221770999333",
        is_active=True,
        is_verified=True,
    )
    user.onboarding_state = UserOnboardingState.PENDING_PARISH_SELECTION
    user.save(update_fields=["onboarding_state"])
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse("api:agenda:event-register", kwargs={"event_id": 999999})

    resp = client.post(url)

    assert resp.status_code == status.HTTP_403_FORBIDDEN

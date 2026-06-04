import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.mass_intentions.models import MassIntention
from apps.users.enums import UserOnboardingState
from apps.users.models import BaseUser


def _make_user(email, pastoral_role="fidele"):
    user = BaseUser.objects.create_user(
        email=email,
        password="StrongPassw0rd!",
        role="fidele",
        phone_number=f"+221770{abs(hash(email)) % 1_000_000:06d}",
        is_active=True,
        is_verified=True,
    )
    user.pastoral_role = pastoral_role
    user.onboarding_state = UserOnboardingState.COMPLETED  # onboardé → peut écrire (A1)
    user.save(update_fields=["pastoral_role", "onboarding_state"])
    return user


@pytest.fixture
def fidele_client(db):
    client = APIClient()
    user = _make_user("fidele@test.com", "fidele")
    client.force_authenticate(user=user)
    client._user = user
    return client


@pytest.fixture
def pretre_client(db):
    client = APIClient()
    user = _make_user("pretre@test.com", "pretre")
    client.force_authenticate(user=user)
    client._user = user
    return client


@pytest.mark.django_db
def test_submit_intention_201(fidele_client):
    # B6b : l'intention se rattache par défaut à la paroisse principale du demandeur.
    from apps.org.tests.factories import ChurchFactory
    from apps.users.services_memberships import membership_create

    membership_create(user=fidele_client._user, church=ChurchFactory(), is_primary=True)
    url = reverse("api:mass-intentions:submit")
    resp = fidele_client.post(
        url,
        {
            "intention_type": "for_deceased",
            "intention_text": "Pour le repos de l'âme de Jean Dupont",
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED
    assert MassIntention.objects.filter(requestor=fidele_client._user).count() == 1


@pytest.mark.django_db
def test_submit_intention_requires_auth():
    client = APIClient()
    url = reverse("api:mass-intentions:submit")
    resp = client.post(url, {}, format="json")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_submit_intention_pending_parish_blocked_returns_403():
    # EXPLOIT A1 : un fidèle pur en pending_parish (paroisse non choisie) ne peut
    # PAS soumettre d'intention. Même endpoint/payload que test_submit_intention_201
    # (completed → 201) : seul l'onboarding_state change → le 403 vient de la garde.
    user = BaseUser.objects.create_user(
        email="pending_mi@test.com",
        password="StrongPassw0rd!",
        role="fidele",
        phone_number="+221770999111",
        is_active=True,
        is_verified=True,
    )
    user.onboarding_state = UserOnboardingState.PENDING_PARISH_SELECTION
    user.save(update_fields=["onboarding_state"])
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse("api:mass-intentions:submit")

    resp = client.post(
        url,
        {"intention_type": "for_deceased", "intention_text": "X"},
        format="json",
    )

    assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_my_intentions_list(fidele_client):
    url = reverse("api:mass-intentions:my-list")
    resp = fidele_client.get(url)
    assert resp.status_code == status.HTTP_200_OK
    assert "results" in resp.data


@pytest.mark.django_db
def test_parish_list_requires_clergy(fidele_client):
    url = reverse("api:mass-intentions:parish-list")
    resp = fidele_client.get(url)
    assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_parish_list_accessible_to_pretre(pretre_client):
    url = reverse("api:mass-intentions:parish-list")
    resp = pretre_client.get(url)
    assert resp.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_accept_intention(fidele_client, pretre_client):
    intention = MassIntention.objects.create(
        requestor=fidele_client._user,
        intention_type="for_living",
        intention_text="Pour la guérison de Marie",
    )
    url = reverse("api:mass-intentions:accept", kwargs={"intention_id": intention.pk})
    resp = pretre_client.post(url)
    assert resp.status_code == status.HTTP_200_OK
    intention.refresh_from_db()
    assert intention.status == "accepted"
    assert intention.pretre == pretre_client._user


@pytest.mark.django_db
def test_accept_intention_requires_clergy(fidele_client):
    intention = MassIntention.objects.create(
        requestor=fidele_client._user,
        intention_type="for_living",
        intention_text="Pour la guérison de Marie",
    )
    url = reverse("api:mass-intentions:accept", kwargs={"intention_id": intention.pk})
    resp = fidele_client.post(url)
    assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_celebrate_intention(fidele_client, pretre_client):
    intention = MassIntention.objects.create(
        requestor=fidele_client._user,
        intention_type="for_deceased",
        intention_text="Pour le repos de l'âme",
        pretre=pretre_client._user,
        status="accepted",
    )
    url = reverse("api:mass-intentions:celebrate", kwargs={"intention_id": intention.pk})
    resp = pretre_client.post(url)
    assert resp.status_code == status.HTTP_200_OK
    intention.refresh_from_db()
    assert intention.status == "celebrated"


@pytest.mark.django_db
def test_decline_intention(fidele_client, pretre_client):
    intention = MassIntention.objects.create(
        requestor=fidele_client._user,
        intention_type="for_community",
        intention_text="Pour la paroisse entière",
    )
    url = reverse("api:mass-intentions:decline", kwargs={"intention_id": intention.pk})
    resp = pretre_client.post(url, {"notes": "Agenda complet ce mois-ci."}, format="json")
    assert resp.status_code == status.HTTP_200_OK
    intention.refresh_from_db()
    assert intention.status == "declined"

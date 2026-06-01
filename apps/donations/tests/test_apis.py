import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.donations.models import Donation, DonationCampaign
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
def test_list_campaigns_200(fidele_client):
    url = reverse("api:donations:campaign-list-create")
    resp = fidele_client.get(url)
    assert resp.status_code == status.HTTP_200_OK
    assert "results" in resp.data


@pytest.mark.django_db
def test_create_campaign_clergy_201(pretre_client):
    url = reverse("api:donations:campaign-list-create")
    resp = pretre_client.post(
        url,
        {
            "title": "Quête de Pâques",
            "donation_type": "sunday_collection",
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED
    assert DonationCampaign.objects.filter(created_by=pretre_client._user).count() == 1


@pytest.mark.django_db
def test_create_campaign_fidele_400(fidele_client):
    url = reverse("api:donations:campaign-list-create")
    resp = fidele_client.post(
        url,
        {"title": "Don libre", "donation_type": "free_donation"},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_make_donation_201(fidele_client, pretre_client):
    campaign = DonationCampaign.objects.create(
        title="Projet paroissial",
        donation_type="special_project",
        created_by=pretre_client._user,
    )
    url = reverse("api:donations:donate")
    resp = fidele_client.post(
        url,
        {"campaign_id": campaign.pk, "amount": 5000, "payment_provider": "wave"},
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED
    assert Donation.objects.filter(donor=fidele_client._user).count() == 1


@pytest.mark.django_db
def test_my_donations_list(fidele_client):
    url = reverse("api:donations:my-list")
    resp = fidele_client.get(url)
    assert resp.status_code == status.HTTP_200_OK
    assert "results" in resp.data


@pytest.mark.django_db
def test_donations_require_auth():
    client = APIClient()
    url = reverse("api:donations:campaign-list-create")
    resp = client.get(url)
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED

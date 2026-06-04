import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.donations.models import Donation, DonationCampaign
from apps.org.tests.factories import ChurchFactory, ParishFactory
from apps.users.enums import RoleScope, UserOnboardingState, UserRole
from apps.users.models import BaseUser, RoleAssignment


def _cure_with_ra(parish, email):
    """Curé (pastoral_role=pretre) + RoleAssignment(parish_admin) sur `parish`."""
    user = _make_user(email, "pretre")
    RoleAssignment.objects.create(
        user=user, role=UserRole.PARISH_ADMIN, scope=RoleScope.PARISH,
        parish=parish, is_active=True,
    )
    return user


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


# --- A3 — autorité sur la paroisse EFFECTIVE (church_id / scope_id) ----------


@pytest.mark.django_db
def test_campaign_create_via_church_id_of_other_parish_returns_403():
    # EXPLOIT : un curé de A crée une campagne pour une église de la paroisse B.
    parish_a = ParishFactory()
    parish_b = ParishFactory()
    church_b = ChurchFactory(parish=parish_b)
    cure_a = _cure_with_ra(parish_a, "cure_a@test.com")
    client = APIClient()
    client.force_authenticate(user=cure_a)
    url = reverse("api:donations:campaign-list-create")

    resp = client.post(
        url,
        {"title": "X", "donation_type": "free_donation", "church_id": church_b.id},
        format="json",
    )

    assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_campaign_create_via_scope_id_other_parish_returns_403():
    # EXPLOIT : même contournement via scope_type=parish + scope_id d'une autre paroisse.
    parish_a = ParishFactory()
    parish_b = ParishFactory()
    cure_a = _cure_with_ra(parish_a, "cure_a2@test.com")
    client = APIClient()
    client.force_authenticate(user=cure_a)
    url = reverse("api:donations:campaign-list-create")

    resp = client.post(
        url,
        {
            "title": "X",
            "donation_type": "free_donation",
            "scope_type": "parish",
            "scope_id": parish_b.id,
        },
        format="json",
    )

    assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_campaign_create_own_parish_via_church_id_201():
    # Le curé PEUT créer une campagne pour une église de SA paroisse (non sur-bloqué).
    parish_a = ParishFactory()
    church_a = ChurchFactory(parish=parish_a)
    cure_a = _cure_with_ra(parish_a, "cure_own@test.com")
    client = APIClient()
    client.force_authenticate(user=cure_a)
    url = reverse("api:donations:campaign-list-create")

    resp = client.post(
        url,
        {"title": "X", "donation_type": "free_donation", "church_id": church_a.id},
        format="json",
    )

    assert resp.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_make_donation_201(fidele_client, pretre_client):
    campaign = DonationCampaign.objects.create(
        title="Projet paroissial",
        donation_type="special_project",
        created_by=pretre_client._user,
    )
    url = reverse("api:donations:donate")
    # Espèces : le paiement en ligne est désactivé jusqu'à l'IPN (Chantier 5b).
    resp = fidele_client.post(
        url,
        {"campaign_id": campaign.pk, "amount": 5000, "payment_provider": "cash"},
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


@pytest.mark.django_db
def test_make_donation_pending_parish_blocked_returns_403():
    # EXPLOIT A1 : un fidèle pur en pending_parish (paroisse non choisie) ne peut
    # PAS faire de don. Même endpoint que test_make_donation_201 (completed → 201) :
    # seul l'onboarding_state change → le 403 vient de la garde.
    user = BaseUser.objects.create_user(
        email="pending_don@test.com",
        password="StrongPassw0rd!",
        role="fidele",
        phone_number="+221770999222",
        is_active=True,
        is_verified=True,
    )
    user.onboarding_state = UserOnboardingState.PENDING_PARISH_SELECTION
    user.save(update_fields=["onboarding_state"])
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse("api:donations:donate")

    resp = client.post(
        url,
        {"amount": 5000, "payment_provider": "wave"},
        format="json",
    )

    assert resp.status_code == status.HTTP_403_FORBIDDEN

"""
Chantier 2 — Onboarding serveur (set d'églises) + /me enrichi + compat shim.

Couvre :
  - l'API Membership /me/memberships/ (POST batch/single, DELETE, set-primary) ;
  - la transition onboarding_state pilotée par les memberships ;
  - /me : memberships[] + pluriels church_ids/parish_ids/diocese_ids, singuliers =
    principaux (rétro-compat) ; cohérence runtime ⇄ serializer ;
  - la COMPAT (non-régression) : le PATCH legacy primary_parish crée une Membership.

pytest + factory_boy. AAA.
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.org.tests.factories import ChurchFactory, ParishFactory
from apps.users.enums import UserOnboardingState
from apps.users.models import Membership, Profile
from apps.users.selectors import user_get_login_data
from apps.users.serializers import MeOutputSerializer
from apps.users.services_memberships import membership_create
from apps.users.tests.factories import BaseUserFactory, ProfileFactory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pending_fidele():
    """Fidèle email vérifié, en attente de sélection de paroisse."""
    return BaseUserFactory(onboarding_state=UserOnboardingState.PENDING_PARISH_SELECTION)


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    client._user = user
    return client


def _main_church(parish=None):
    return ChurchFactory(
        parish=parish or ParishFactory(), is_main=True, church_type="paroissiale"
    )


# ---------------------------------------------------------------------------
# Onboarding piloté par les memberships
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_onboarding_add_multiple_churches_across_parishes_sets_completed():
    user = _pending_fidele()
    ProfileFactory(user=user, primary_parish=None)
    church_a = _main_church()
    church_b = _main_church()
    client = _client(user)
    url = reverse("api:users:me-membership-list-create")

    resp = client.post(url, {"church_ids": [church_a.id, church_b.id]}, format="json")

    assert resp.status_code == 201
    memberships = Membership.objects.filter(user=user)
    assert memberships.count() == 2
    assert memberships.filter(is_primary=True).count() == 1
    user.refresh_from_db()
    assert user.onboarding_state == UserOnboardingState.COMPLETED

    # /me reflète memberships[] et les 3 ensembles d'ids.
    me = user_get_login_data(user=user)
    assert len(me["memberships"]) == 2
    assert set(me["church_ids"]) == {church_a.id, church_b.id}
    assert set(me["parish_ids"]) == {church_a.parish_id, church_b.parish_id}
    assert set(me["diocese_ids"]) == {
        church_a.parish.diocese_id,
        church_b.parish.diocese_id,
    }


@pytest.mark.django_db
def test_onboarding_batch_duplicate_church_ids_returns_400():
    # Doublon dans church_ids → 400 (jamais 500 via violation unique en base).
    user = _pending_fidele()
    church = _main_church()
    client = _client(user)
    url = reverse("api:users:me-membership-list-create")

    resp = client.post(url, {"church_ids": [church.id, church.id]}, format="json")

    assert resp.status_code == 400
    assert Membership.objects.filter(user=user).count() == 0


@pytest.mark.django_db
def test_completed_requires_at_least_one_membership():
    user = _pending_fidele()
    # Sans appartenance : pas completed.
    assert user.onboarding_state == UserOnboardingState.PENDING_PARISH_SELECTION

    membership_create(user=user, church=_main_church(), is_primary=True)

    user.refresh_from_db()
    assert user.onboarding_state == UserOnboardingState.COMPLETED
    assert Membership.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_remove_last_membership_reverts_to_pending_parish():
    user = _pending_fidele()
    client = _client(user)
    m = membership_create(user=user, church=_main_church(), is_primary=True)
    user.refresh_from_db()
    assert user.onboarding_state == UserOnboardingState.COMPLETED

    url = reverse("api:users:me-membership-delete", kwargs={"membership_id": m.id})
    resp = client.delete(url)

    assert resp.status_code == 204
    user.refresh_from_db()
    assert user.onboarding_state == UserOnboardingState.PENDING_PARISH_SELECTION


# ---------------------------------------------------------------------------
# /me enrichi
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_me_returns_memberships_and_plural_ids():
    user = _pending_fidele()
    ProfileFactory(user=user, primary_parish=None)
    church = _main_church()
    membership_create(user=user, church=church, is_primary=True)
    client = _client(user)

    resp = client.get(reverse("api:users:me-detail"))

    assert resp.status_code == 200
    body = resp.json()
    assert "memberships" in body and len(body["memberships"]) == 1
    entry = body["memberships"][0]
    assert entry["church"]["id"] == church.id
    assert entry["parish"]["id"] == church.parish_id
    assert entry["diocese"]["id"] == church.parish.diocese_id
    assert entry["is_primary"] is True
    assert body["church_ids"] == [church.id]
    assert body["parish_ids"] == [church.parish_id]
    assert body["diocese_ids"] == [church.parish.diocese_id]


@pytest.mark.django_db
def test_me_singular_fields_are_primary():
    user = _pending_fidele()
    ProfileFactory(user=user, primary_parish=None)
    primary = _main_church()
    secondary = _main_church()
    membership_create(user=user, church=primary, is_primary=True)
    membership_create(user=user, church=secondary, is_primary=False)

    # Le signal remplit diocese/province via .update() (hors objet mémoire) ; en
    # conditions réelles request.user est rechargé à chaque requête → on simule.
    user.refresh_from_db()
    me = user_get_login_data(user=user)

    # Singuliers = principaux (rétro-compat front actuel).
    assert me["diocese"]["id"] == primary.parish.diocese_id
    assert me["province"]["id"] == primary.parish.diocese.province_id
    assert me["profile"]["primary_parish"]["id"] == primary.parish_id


@pytest.mark.django_db
def test_me_serializer_matches_runtime():
    user = _pending_fidele()
    ProfileFactory(user=user, primary_parish=None)
    membership_create(user=user, church=_main_church(), is_primary=True)
    membership_create(user=user, church=_main_church(), is_primary=False)

    runtime = user_get_login_data(user=user)
    serialized = MeOutputSerializer(runtime).data

    assert serialized["church_ids"] == runtime["church_ids"]
    assert serialized["parish_ids"] == runtime["parish_ids"]
    assert serialized["diocese_ids"] == runtime["diocese_ids"]
    assert len(serialized["memberships"]) == len(runtime["memberships"])
    for s, r in zip(serialized["memberships"], runtime["memberships"]):
        assert s["church"]["id"] == r["church"]["id"]
        assert s["parish"]["id"] == r["parish"]["id"]
        assert s["diocese"]["id"] == r["diocese"]["id"]
        assert s["is_primary"] == r["is_primary"]


# ---------------------------------------------------------------------------
# COMPAT — le PATCH legacy primary_parish crée une Membership
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_legacy_patch_primary_parish_creates_primary_membership_and_completes():
    user = _pending_fidele()
    ProfileFactory(user=user, primary_parish=None)
    parish = ParishFactory()
    main_church = ChurchFactory(parish=parish, is_main=True, church_type="paroissiale")
    client = _client(user)

    resp = client.patch(
        reverse("api:users:me-update"), {"primary_parish": parish.id}, format="json"
    )

    assert resp.status_code == 200
    # Le PATCH a créé une appartenance principale sur l'église is_main.
    m = Membership.objects.get(user=user)
    assert m.church_id == main_church.id
    assert m.is_primary is True
    user.refresh_from_db()
    assert user.onboarding_state == UserOnboardingState.COMPLETED
    # Le signal a mirroré primary_parish.
    profile = Profile.objects.get(user=user)
    assert profile.primary_parish_id == parish.id


@pytest.mark.django_db
def test_legacy_patch_primary_parish_without_main_church_raises():
    user = _pending_fidele()
    ProfileFactory(user=user, primary_parish=None)
    parish = ParishFactory()  # AUCUNE église is_main
    client = _client(user)

    resp = client.patch(
        reverse("api:users:me-update"), {"primary_parish": parish.id}, format="json"
    )

    assert resp.status_code == 400
    assert not Membership.objects.filter(user=user).exists()


# ---------------------------------------------------------------------------
# Endpoints set-primary / remove / autorisation propriétaire
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_set_primary_endpoint_demotes_previous():
    user = _pending_fidele()
    client = _client(user)
    m_a = membership_create(user=user, church=_main_church(), is_primary=True)
    m_b = membership_create(user=user, church=_main_church(), is_primary=False)

    url = reverse("api:users:me-membership-set-primary", kwargs={"membership_id": m_b.id})
    resp = client.patch(url)

    assert resp.status_code == 200
    m_a.refresh_from_db()
    m_b.refresh_from_db()
    assert m_b.is_primary is True
    assert m_a.is_primary is False


@pytest.mark.django_db
def test_remove_endpoint_promotes_oldest():
    user = _pending_fidele()
    client = _client(user)
    m_a = membership_create(user=user, church=_main_church(), is_primary=True)
    m_b = membership_create(user=user, church=_main_church())
    membership_create(user=user, church=_main_church())

    url = reverse("api:users:me-membership-delete", kwargs={"membership_id": m_a.id})
    resp = client.delete(url)

    assert resp.status_code == 204
    m_b.refresh_from_db()
    assert m_b.is_primary is True
    assert Membership.objects.filter(user=user, is_primary=True).count() == 1


@pytest.mark.django_db
def test_user_cannot_manage_other_users_memberships():
    owner = _pending_fidele()
    intruder = _pending_fidele()
    m = membership_create(user=owner, church=_main_church(), is_primary=True)
    client = _client(intruder)

    del_url = reverse("api:users:me-membership-delete", kwargs={"membership_id": m.id})
    sp_url = reverse(
        "api:users:me-membership-set-primary", kwargs={"membership_id": m.id}
    )

    assert client.delete(del_url).status_code == 403
    assert client.patch(sp_url).status_code == 403
    assert Membership.objects.filter(pk=m.pk).exists()  # rien supprimé

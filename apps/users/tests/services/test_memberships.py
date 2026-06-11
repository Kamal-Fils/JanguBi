"""
Tests des appartenances ecclésiales (Membership) — Chantier 1, couche additive.

Couvre :
  - le modèle + ses 2 contraintes (unicité user+church, au plus une principale) ;
  - les services membership_create / membership_set_primary / membership_remove
    (pattern de démotion atomique calqué sur services_roles) ;
  - le signal post_save/post_delete (recalcul diocese/province + miroir
    Profile.primary_parish depuis l'église principale) ;
  - la NON-RÉGRESSION du chemin historique primary_parish + son signal.

Pattern AAA. pytest + factory_boy.
"""

import pytest
from django.db import IntegrityError, transaction

from apps.core.exceptions import ApplicationError
from apps.org.tests.factories import ChurchFactory, ParishFactory
from apps.users.models import Membership, Profile
from apps.users.services_memberships import (
    membership_create,
    membership_remove,
    membership_set_primary,
)
from apps.users.tests.factories import BaseUserFactory, ProfileFactory

# ---------------------------------------------------------------------------
# Modèle + contraintes
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_user_can_have_multiple_memberships_across_parishes():
    # Arrange
    user = BaseUserFactory()
    church_a = ChurchFactory()
    church_b = ChurchFactory()

    # Act
    membership_create(user=user, church=church_a, is_primary=True)
    membership_create(user=user, church=church_b, is_primary=False)

    # Assert : deux paroisses distinctes, exactement une principale.
    memberships = Membership.objects.filter(user=user)
    assert memberships.count() == 2
    assert memberships.filter(is_primary=True).count() == 1
    assert church_a.parish_id != church_b.parish_id
    assert set(memberships.values_list("church__parish_id", flat=True)) == {
        church_a.parish_id,
        church_b.parish_id,
    }


@pytest.mark.django_db
def test_at_most_one_primary_per_user():
    user = BaseUserFactory()
    church_a = ChurchFactory()
    church_b = ChurchFactory()

    # Via service : une 2e principale démote la 1re (pas deux principales).
    membership_create(user=user, church=church_a, is_primary=True)
    membership_create(user=user, church=church_b, is_primary=True)
    primaries = Membership.objects.filter(user=user, is_primary=True)
    assert primaries.count() == 1
    assert primaries.first().church_id == church_b.id

    # Violation DB directe (contournant le service) → IntegrityError.
    other = BaseUserFactory()
    Membership.objects.create(user=other, church=ChurchFactory(), is_primary=True)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Membership.objects.create(user=other, church=ChurchFactory(), is_primary=True)


@pytest.mark.django_db
def test_unique_membership_user_church():
    user = BaseUserFactory()
    church = ChurchFactory()
    membership_create(user=user, church=church, is_primary=True)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Membership.objects.create(user=user, church=church, is_primary=False)


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_first_membership_is_auto_primary():
    # La toute 1re appartenance est principale d'office, même si is_primary=False.
    user = BaseUserFactory()
    membership = membership_create(user=user, church=ChurchFactory(), is_primary=False)
    assert membership.is_primary is True


@pytest.mark.django_db
def test_set_primary_demotes_previous_atomically():
    user = BaseUserFactory()
    m_a = membership_create(user=user, church=ChurchFactory(), is_primary=True)
    m_b = membership_create(user=user, church=ChurchFactory(), is_primary=False)

    membership_set_primary(user=user, membership=m_b)

    m_a.refresh_from_db()
    m_b.refresh_from_db()
    assert m_b.is_primary is True
    assert m_a.is_primary is False
    assert Membership.objects.filter(user=user, is_primary=True).count() == 1


@pytest.mark.django_db
def test_remove_primary_promotes_oldest_remaining():
    user = BaseUserFactory()
    m_a = membership_create(user=user, church=ChurchFactory(), is_primary=True)
    m_b = membership_create(user=user, church=ChurchFactory())  # plus ancienne restante
    m_c = membership_create(user=user, church=ChurchFactory())

    membership_remove(user=user, membership=m_a)

    assert not Membership.objects.filter(pk=m_a.pk).exists()
    m_b.refresh_from_db()
    m_c.refresh_from_db()
    assert m_b.is_primary is True
    assert m_c.is_primary is False
    assert Membership.objects.filter(user=user, is_primary=True).count() == 1


@pytest.mark.django_db
def test_remove_last_membership_leaves_no_primary():
    user = BaseUserFactory()
    m = membership_create(user=user, church=ChurchFactory(), is_primary=True)
    membership_remove(user=user, membership=m)
    assert Membership.objects.filter(user=user).count() == 0


@pytest.mark.django_db
def test_membership_create_rejects_inactive_church():
    user = BaseUserFactory()
    inactive = ChurchFactory(is_active=False)
    with pytest.raises(ApplicationError):
        membership_create(user=user, church=inactive)


@pytest.mark.django_db
def test_membership_remove_rejects_foreign_membership():
    owner = BaseUserFactory()
    intruder = BaseUserFactory()
    m = membership_create(user=owner, church=ChurchFactory(), is_primary=True)
    with pytest.raises(ApplicationError):
        membership_remove(user=intruder, membership=m)


# ---------------------------------------------------------------------------
# Signal (recalcul hiérarchie + miroir primary_parish)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_signal_updates_diocese_province_and_mirrors_primary_parish_from_primary_church():
    user = BaseUserFactory()
    ProfileFactory(user=user, primary_parish=None)
    church = ChurchFactory(is_main=True, church_type="paroissiale")

    membership_create(user=user, church=church, is_primary=True)

    user.refresh_from_db()
    assert user.diocese_id == church.parish.diocese_id
    assert user.province_id == church.parish.diocese.province_id
    profile = Profile.objects.get(user=user)
    assert profile.primary_parish_id == church.parish_id


@pytest.mark.django_db
def test_signal_clears_when_last_membership_removed():
    user = BaseUserFactory()
    ProfileFactory(user=user, primary_parish=None)
    church = ChurchFactory(is_main=True, church_type="paroissiale")
    m = membership_create(user=user, church=church, is_primary=True)

    membership_remove(user=user, membership=m)

    user.refresh_from_db()
    assert user.diocese_id is None
    assert user.province_id is None
    profile = Profile.objects.get(user=user)
    assert profile.primary_parish_id is None


@pytest.mark.django_db
def test_set_primary_re_mirrors_to_the_new_primary_parish():
    # Changer d'appartenance principale doit re-piloter diocese/province + le miroir.
    user = BaseUserFactory()
    ProfileFactory(user=user, primary_parish=None)
    church_a = ChurchFactory(is_main=True, church_type="paroissiale")
    church_b = ChurchFactory(is_main=True, church_type="paroissiale")
    membership_create(user=user, church=church_a, is_primary=True)
    m_b = membership_create(user=user, church=church_b, is_primary=False)

    membership_set_primary(user=user, membership=m_b)

    user.refresh_from_db()
    assert user.diocese_id == church_b.parish.diocese_id
    profile = Profile.objects.get(user=user)
    assert profile.primary_parish_id == church_b.parish_id


# ---------------------------------------------------------------------------
# NON-RÉGRESSION : le chemin historique primary_parish reste fonctionnel
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_legacy_primary_parish_path_still_syncs_diocese_province():
    # Le signal legacy (post_save Profile) continue de remplir diocese/province
    # depuis primary_parish — inchangé au Chantier 1 (chemin parallèle).
    user = BaseUserFactory()
    parish = ParishFactory()
    profile = ProfileFactory(user=user, primary_parish=None)

    profile.primary_parish = parish
    profile.save()

    user.refresh_from_db()
    assert user.diocese_id == parish.diocese_id
    assert user.province_id == parish.diocese.province_id

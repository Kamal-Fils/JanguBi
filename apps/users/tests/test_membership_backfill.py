"""
Tests de la logique de backfill de la migration data (Chantier 1).

La logique est extraite dans ``apps.users.migration_ops.backfill_memberships``
(injection des modèles) pour être testable directement avec les modèles réels —
au dernier état de migration, modèle réel == modèle historique.

Garantit notamment le comportement DÉFENSIF : une paroisse sans église
principale (``is_main``) est flaguée et sautée, jamais une exception.
"""

import pytest

from apps.org.models import Church
from apps.org.tests.factories import ChurchFactory, ParishFactory
from apps.users.migration_ops import backfill_memberships
from apps.users.models import Membership, Profile
from apps.users.tests.factories import BaseUserFactory, ProfileFactory


@pytest.mark.django_db
def test_migration_backfills_one_primary_membership_from_primary_parish():
    # Arrange : profil rattaché à une paroisse qui possède bien son église principale.
    user = BaseUserFactory()
    parish = ParishFactory()
    main_church = ChurchFactory(parish=parish, is_main=True, church_type="paroissiale")
    ProfileFactory(user=user, primary_parish=parish)

    # Act
    created, flagged = backfill_memberships(
        Profile=Profile, Church=Church, Membership=Membership
    )

    # Assert
    assert created == 1
    assert flagged == []
    membership = Membership.objects.get(user=user)
    assert membership.church_id == main_church.id
    assert membership.is_primary is True


@pytest.mark.django_db
def test_migration_flags_and_skips_parish_without_main_church():
    # Arrange : la paroisse n'a AUCUNE église principale → cas défensif.
    user = BaseUserFactory()
    parish = ParishFactory()  # pas de ChurchFactory(is_main=True)
    ProfileFactory(user=user, primary_parish=parish)

    # Act — ne doit PAS lever d'exception.
    created, flagged = backfill_memberships(
        Profile=Profile, Church=Church, Membership=Membership
    )

    # Assert : aucune appartenance créée, paroisse flaguée pour reprise manuelle.
    assert created == 0
    assert Membership.objects.filter(user=user).count() == 0
    assert len(flagged) == 1
    assert flagged[0]["user_id"] == user.id
    assert flagged[0]["parish_id"] == parish.id
    assert flagged[0]["parish_name"] == parish.name


@pytest.mark.django_db
def test_migration_backfill_is_idempotent():
    # Rejouer le backfill ne crée pas de doublon (get_or_create sur user+church).
    user = BaseUserFactory()
    parish = ParishFactory()
    ChurchFactory(parish=parish, is_main=True, church_type="paroissiale")
    ProfileFactory(user=user, primary_parish=parish)

    backfill_memberships(Profile=Profile, Church=Church, Membership=Membership)
    created_2, flagged_2 = backfill_memberships(
        Profile=Profile, Church=Church, Membership=Membership
    )

    assert created_2 == 0
    assert flagged_2 == []
    assert Membership.objects.filter(user=user).count() == 1

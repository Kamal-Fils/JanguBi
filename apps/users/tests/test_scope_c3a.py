"""
Chantier 3a (côté users) — get_scope_ids dérivé des appartenances + suppression
de followed_parishes. Le signal legacy primary_parish reste fonctionnel.
"""

import pytest
from django.core.exceptions import FieldDoesNotExist

from apps.org.tests.factories import ChurchFactory, ParishFactory
from apps.users.models import BaseUser
from apps.users.services_memberships import membership_create
from apps.users.tests.factories import BaseUserFactory, ProfileFactory


@pytest.mark.django_db
def test_get_scope_ids_returns_plural_sets_from_memberships():
    # 2 appartenances → 2 églises / 2 paroisses / 2 diocèses (ensembles pluriels).
    user = BaseUserFactory()
    church_a = ChurchFactory()
    church_b = ChurchFactory()
    membership_create(user=user, church=church_a, is_primary=True)
    membership_create(user=user, church=church_b)

    scope = user.get_scope_ids()

    assert set(scope["church_ids"]) == {church_a.id, church_b.id}
    assert set(scope["parish_ids"]) == {church_a.parish_id, church_b.parish_id}
    assert set(scope["diocese_ids"]) == {
        church_a.parish.diocese_id,
        church_b.parish.diocese_id,
    }
    # Plus de scalaires diocese_id/province_id (remplacés par les pluriels).
    assert "diocese_id" not in scope
    assert "province_id" not in scope


@pytest.mark.django_db
def test_get_scope_ids_empty_for_user_without_membership():
    user = BaseUserFactory()
    assert user.get_scope_ids() == {"church_ids": [], "parish_ids": [], "diocese_ids": []}


@pytest.mark.django_db
def test_followed_parishes_removed_and_unreferenced():
    # Le M2M followed_parishes n'existe plus sur le modèle.
    with pytest.raises(FieldDoesNotExist):
        BaseUser._meta.get_field("followed_parishes")


@pytest.mark.django_db
def test_legacy_primary_parish_signal_still_works():
    # NON-RÉGRESSION : le signal legacy (Profile.primary_parish via save) remplit
    # toujours diocese/province sur BaseUser.
    user = BaseUserFactory()
    parish = ParishFactory()
    profile = ProfileFactory(user=user, primary_parish=None)

    profile.primary_parish = parish
    profile.save()

    user.refresh_from_db()
    assert user.diocese_id == parish.diocese_id
    assert user.province_id == parish.diocese.province_id

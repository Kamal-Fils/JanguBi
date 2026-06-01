"""
Chantier 6a — verrou de l'invariant d'onboarding.

completed ⇔ ≥ 1 appartenance : l'état COMPLETED est piloté EXCLUSIVEMENT par la
présence d'appartenances (via _recompute_onboarding_state), jamais par primary_parish.
Verrouille la suppression de l'ancienne logique « completed basé sur primary_parish ».
"""

import pytest

from apps.org.tests.factories import ChurchFactory
from apps.users.enums import UserOnboardingState
from apps.users.services_memberships import membership_create, membership_remove
from apps.users.tests.factories import BaseUserFactory


@pytest.mark.django_db
def test_completed_iff_at_least_one_membership():
    user = BaseUserFactory(onboarding_state=UserOnboardingState.PENDING_PARISH_SELECTION)

    # 0 appartenance → PAS completed.
    assert user.onboarding_state != UserOnboardingState.COMPLETED

    # ≥ 1 appartenance → completed.
    m = membership_create(user=user, church=ChurchFactory(), is_primary=True)
    user.refresh_from_db()
    assert user.onboarding_state == UserOnboardingState.COMPLETED

    # Retrait de la dernière → retour pending_parish (plus aucune appartenance).
    membership_remove(user=user, membership=m)
    user.refresh_from_db()
    assert user.onboarding_state == UserOnboardingState.PENDING_PARISH_SELECTION


@pytest.mark.django_db
def test_completed_not_set_by_primary_parish_alone():
    # Un Profile.primary_parish renseigné SANS appartenance ne complète pas l'onboarding
    # (l'ancienne logique a été retirée au Chantier 2).
    from apps.org.tests.factories import ParishFactory
    from apps.users.tests.factories import ProfileFactory

    user = BaseUserFactory(onboarding_state=UserOnboardingState.PENDING_PARISH_SELECTION)
    ProfileFactory(user=user, primary_parish=ParishFactory())
    user.refresh_from_db()
    assert user.onboarding_state == UserOnboardingState.PENDING_PARISH_SELECTION

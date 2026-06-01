"""Services d'écriture pour les appartenances ecclésiales (Membership).

Couche ADDITIVE (Chantier 1). Calqués sur ``services_roles`` : démotion de
l'éventuelle appartenance principale AVANT l'insert/la promotion, le tout dans
``@transaction.atomic`` pour respecter la contrainte d'unicité partielle
``unique_primary_membership_per_user``.

Invariant tenu par ces services : tant qu'il reste ≥ 1 appartenance pour un
utilisateur, exactement une est ``is_primary``.
"""

from __future__ import annotations

from django.db import transaction

from apps.core.exceptions import ApplicationError
from apps.users.enums import UserOnboardingState
from apps.users.models import Membership


def _recompute_onboarding_state(user) -> None:
    """Aligne ``onboarding_state`` sur la présence d'appartenances (Chantier 2).

    ≥ 1 appartenance → ``completed`` ; plus aucune → retour ``pending_parish``.
    On ne dégrade jamais ``pending_email`` (email pas encore vérifié) tant qu'il
    n'y a pas d'appartenance. Écrit via ``save(update_fields)`` seulement en cas
    de changement effectif.
    """
    has_membership = Membership.objects.filter(user=user).exists()
    if has_membership:
        target = UserOnboardingState.COMPLETED
    elif user.onboarding_state == UserOnboardingState.PENDING_EMAIL_VERIFICATION:
        return
    else:
        target = UserOnboardingState.PENDING_PARISH_SELECTION

    if user.onboarding_state != target:
        user.onboarding_state = target
        user.save(update_fields=["onboarding_state", "updated_at"])


@transaction.atomic
def membership_create(*, user, church, is_primary: bool = False) -> Membership:
    """Rattache ``user`` à ``church``.

    La 1re appartenance d'un utilisateur est principale d'office. Si ``is_primary``
    est demandé (ou imposé car 1re), l'éventuelle principale existante est démotée
    avant l'insert. La présence d'une appartenance termine l'onboarding.
    """
    if church is None:
        raise ApplicationError("Une église est requise pour créer une appartenance.")
    if not church.is_active:
        raise ApplicationError("L'église ciblée est inactive.")

    # 1re appartenance → principale d'office (invariant : ≥ 1 appartenance ⇒ 1 principale).
    is_first = not Membership.objects.filter(user=user).exists()
    make_primary = is_primary or is_first

    if make_primary:
        # Démote l'éventuelle principale AVANT l'insert (respecte la contrainte d'unicité).
        Membership.objects.filter(user=user, is_primary=True).update(is_primary=False)

    membership = Membership.objects.create(user=user, church=church, is_primary=make_primary)
    _recompute_onboarding_state(user)
    return membership


@transaction.atomic
def memberships_create_batch(*, user, church_ids: list[int]) -> list[Membership]:
    """Rattache ``user`` à plusieurs églises (cascade onboarding). La 1re devient
    principale d'office (cf. ``membership_create``)."""
    from apps.org.models import Church

    created: list[Membership] = []
    for church_id in church_ids:
        church = Church.objects.filter(pk=church_id).first()
        if church is None:
            raise ApplicationError(f"Église {church_id} introuvable.")
        created.append(membership_create(user=user, church=church, is_primary=False))
    return created


@transaction.atomic
def membership_set_primary(*, user, membership: Membership) -> Membership:
    """Promeut ``membership`` comme appartenance principale (démote l'ancienne)."""
    if membership.user_id != user.pk:
        raise ApplicationError("Cette appartenance n'appartient pas à l'utilisateur.")

    # Démote toutes les autres principales de l'utilisateur, puis promeut celle-ci.
    Membership.objects.filter(user=user, is_primary=True).exclude(pk=membership.pk).update(
        is_primary=False
    )
    if not membership.is_primary:
        membership.is_primary = True
        membership.save(update_fields=["is_primary", "updated_at"])
    return membership


@transaction.atomic
def membership_remove(*, user, membership: Membership) -> None:
    """Supprime ``membership``. Si elle était principale et qu'il reste des
    appartenances, promeut la plus ancienne (maintien de l'invariant)."""
    if membership.user_id != user.pk:
        raise ApplicationError("Cette appartenance n'appartient pas à l'utilisateur.")

    was_primary = membership.is_primary
    membership.delete()

    if was_primary:
        next_primary = (
            Membership.objects.filter(user=user).order_by("created_at", "pk").first()
        )
        if next_primary is not None:
            next_primary.is_primary = True
            next_primary.save(update_fields=["is_primary", "updated_at"])

    _recompute_onboarding_state(user)

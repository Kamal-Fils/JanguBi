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
from apps.users.models import Membership


@transaction.atomic
def membership_create(*, user, church, is_primary: bool = False) -> Membership:
    """Rattache ``user`` à ``church``.

    La 1re appartenance d'un utilisateur est principale d'office. Si ``is_primary``
    est demandé (ou imposé car 1re), l'éventuelle principale existante est démotée
    avant l'insert.
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

    return Membership.objects.create(user=user, church=church, is_primary=make_primary)


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

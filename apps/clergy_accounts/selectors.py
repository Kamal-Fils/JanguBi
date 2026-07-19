from django.db.models import QuerySet
from django.utils import timezone

from apps.users.models import BaseUser

from .models import ClergicalInvitation


def invitation_list(*, created_by: BaseUser | None = None, status: str | None = None) -> QuerySet[ClergicalInvitation]:
    qs = ClergicalInvitation.objects.select_related("created_by", "diocese", "accepted_by")

    if created_by is not None:
        qs = qs.filter(created_by=created_by)

    if status is not None:
        qs = qs.filter(status=status)

    return qs


def invitation_get_for_creator(*, invitation_id: int, creator: BaseUser) -> ClergicalInvitation | None:
    """Une invitation par ID, restreinte à son émetteur (``None`` si absente/étrangère).

    Isole l'accès ORM hors de la couche API. Sémantique identique au
    ``ClergicalInvitation.objects.get(pk=…, created_by=…)`` qu'elle remplace :
    une invitation créée par quelqu'un d'autre est traitée comme introuvable
    (pas de fuite d'existence).
    """
    return ClergicalInvitation.objects.filter(pk=invitation_id, created_by=creator).first()


def invitation_get_by_token(*, token: str) -> ClergicalInvitation:
    from apps.core.exceptions import ApplicationError

    try:
        return ClergicalInvitation.objects.select_related("diocese").get(token=token)
    except ClergicalInvitation.DoesNotExist:
        raise ApplicationError("Invitation introuvable.")


def invitation_expire_stale() -> int:
    """Mark pending invitations past their expiry date as expired. Returns count updated."""
    return ClergicalInvitation.objects.filter(
        status=ClergicalInvitation.Status.PENDING,
        expires_at__lt=timezone.now(),
    ).update(status=ClergicalInvitation.Status.EXPIRED)

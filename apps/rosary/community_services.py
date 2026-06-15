from django.db import transaction

from apps.core.exceptions import ApplicationError

CLERGY_ROLES = {"religieux", "diacre", "pretre", "eveque", "archeveque"}


@transaction.atomic
def community_rosary_start(*, initiator, mystery_group_id: int | None = None, intention: str = ""):
    from apps.rosary.models import CommunityRosary

    role = getattr(initiator, "pastoral_role", None)
    if role not in CLERGY_ROLES:
        raise ApplicationError("Seul le clergé peut initier un chapelet communautaire.")

    return CommunityRosary.objects.create(
        initiator=initiator,
        mystery_group_id=mystery_group_id,
        intention=intention,
        status=CommunityRosary.Status.ACTIVE,
    )


@transaction.atomic
def community_rosary_join(*, rosary, user):
    from apps.rosary.models import RosaryParticipant

    if rosary.status != "active":
        raise ApplicationError("Ce chapelet n'est plus actif.")
    participant, _ = RosaryParticipant.objects.get_or_create(rosary=rosary, user=user)
    return participant


@transaction.atomic
def community_rosary_submit_intention(*, rosary, user, text: str):
    from apps.rosary.models import RosaryIntention

    if rosary.status != "active":
        raise ApplicationError("Ce chapelet n'est plus actif.")
    if not text.strip():
        raise ApplicationError("L'intention ne peut pas être vide.")
    return RosaryIntention.objects.create(rosary=rosary, submitted_by=user, text=text)


@transaction.atomic
def community_rosary_end(*, rosary, user):
    from django.utils import timezone

    if rosary.initiator_id != user.pk:
        raise ApplicationError("Seul l'initiateur peut terminer le chapelet.")
    rosary.status = "completed"
    rosary.ended_at = timezone.now()
    rosary.save(update_fields=["status", "ended_at", "updated_at"])
    return rosary


def community_rosary_list_active():
    from apps.rosary.models import CommunityRosary

    return CommunityRosary.objects.filter(status="active").select_related("initiator", "mystery_group").order_by("-started_at")


def community_rosary_get(*, rosary_id: int):
    from apps.rosary.models import CommunityRosary

    try:
        return CommunityRosary.objects.select_related("initiator", "mystery_group").get(pk=rosary_id)
    except CommunityRosary.DoesNotExist:
        raise ApplicationError("Session de chapelet introuvable.")

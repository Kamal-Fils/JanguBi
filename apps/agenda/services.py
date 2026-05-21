from django.db import transaction

from apps.core.exceptions import ApplicationError


CLERGY_ROLES = {"diacre", "pretre", "eveque", "archeveque", "religieux"}
BISHOP_ROLES = {"eveque", "archeveque"}
ADMIN_ROLES = {"super_admin", "province_admin", "diocese_admin", "parish_admin", "church_admin"}


def _can_create_event(user) -> bool:
    return (
        getattr(user, "pastoral_role", None) in CLERGY_ROLES
        or getattr(user, "role", None) in ADMIN_ROLES
    )


@transaction.atomic
def event_create(
    *,
    organizer,
    title: str,
    description: str = "",
    event_type: str,
    start_at,
    end_at,
    location: str = "",
    scope_type: str = "global",
    scope_id: int | None = None,
    max_participants: int | None = None,
):
    from apps.agenda.models import Event

    if not _can_create_event(organizer):
        raise ApplicationError("Seul le clergé ou les administrateurs peuvent créer des événements.")
    if end_at <= start_at:
        raise ApplicationError("La date de fin doit être après la date de début.")
    return Event.objects.create(
        organizer=organizer,
        title=title,
        description=description,
        event_type=event_type,
        start_at=start_at,
        end_at=end_at,
        location=location,
        scope_type=scope_type,
        scope_id=scope_id,
        max_participants=max_participants,
    )


@transaction.atomic
def event_register(*, event, user):
    from apps.agenda.models import EventRegistration

    if event.max_participants is not None:
        count = event.registrations.count()
        if count >= event.max_participants:
            raise ApplicationError("Cet événement est complet.")
    registration, created = EventRegistration.objects.get_or_create(event=event, user=user)
    if not created:
        raise ApplicationError("Vous êtes déjà inscrit à cet événement.")
    return registration

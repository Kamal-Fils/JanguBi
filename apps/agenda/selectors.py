from django.db.models import QuerySet
from django.utils import timezone


def event_list(*, scope_type: str | None = None, event_type: str | None = None, upcoming_only: bool = True) -> QuerySet:
    from apps.agenda.models import Event

    qs = Event.objects.select_related("organizer")
    if upcoming_only:
        qs = qs.filter(start_at__gte=timezone.now())
    if scope_type:
        qs = qs.filter(scope_type=scope_type)
    if event_type:
        qs = qs.filter(event_type=event_type)
    return qs.order_by("start_at")


def event_get(*, event_id: int):
    from apps.agenda.models import Event
    from apps.core.exceptions import ApplicationError

    try:
        return Event.objects.prefetch_related("registrations__user").select_related("organizer").get(pk=event_id)
    except Event.DoesNotExist:
        raise ApplicationError("Événement introuvable.")


def event_registrations_list(*, event_id: int) -> QuerySet:
    from apps.agenda.models import EventRegistration

    return EventRegistration.objects.filter(event_id=event_id).select_related("user").order_by("registered_at")

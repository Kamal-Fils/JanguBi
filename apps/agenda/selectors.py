from django.db.models import BooleanField, Exists, OuterRef, QuerySet, Value
from django.utils import timezone


def _annotate_is_registered(qs: QuerySet, user) -> QuerySet:
    """Annote chaque événement avec `is_registered` pour l'utilisateur donné.

    Évite le N+1 (un seul EXISTS corrélé). Si l'utilisateur est anonyme/absent,
    annote False pour que le serializer dispose toujours du champ.
    """
    from apps.agenda.models import EventRegistration

    if user is not None and getattr(user, "is_authenticated", False):
        return qs.annotate(
            is_registered=Exists(
                EventRegistration.objects.filter(event=OuterRef("pk"), user=user)
            )
        )
    return qs.annotate(is_registered=Value(False, output_field=BooleanField()))


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


def event_list_for_user(*, user, event_type: str | None = None, upcoming_only: bool = True) -> QuerySet:
    """Feed agenda scopé aux appartenances de l'utilisateur (Chantier 3b) :
    global ∪ église ∪ paroisse ∪ diocèse, via le helper générique du 3a."""
    from apps.agenda.models import Event
    from apps.users.scoping import get_scoped_queryset

    qs = Event.objects.select_related("organizer")
    if upcoming_only:
        qs = qs.filter(start_at__gte=timezone.now())
    if event_type:
        qs = qs.filter(event_type=event_type)
    qs = get_scoped_queryset(qs, user)
    qs = _annotate_is_registered(qs, user)
    return qs.order_by("start_at")


def event_get(*, event_id: int, user=None):
    from apps.agenda.models import Event
    from apps.core.exceptions import ApplicationError

    qs = Event.objects.prefetch_related("registrations__user").select_related("organizer")
    qs = _annotate_is_registered(qs, user)
    try:
        return qs.get(pk=event_id)
    except Event.DoesNotExist:
        raise ApplicationError("Événement introuvable.")


def event_registrations_list(*, event_id: int) -> QuerySet:
    from apps.agenda.models import EventRegistration

    return EventRegistration.objects.filter(event_id=event_id).select_related("user").order_by("registered_at")

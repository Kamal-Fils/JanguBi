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


def _check_event_scope_consistency(scope_type, scope_parish_id, scope_diocese_id, scope_church_id):
    from apps.agenda.models import Event

    if scope_type == Event.ScopeType.PARISH and not scope_parish_id:
        raise ApplicationError("Un événement de portée 'paroisse' requiert un scope_id (paroisse).")
    if scope_type == Event.ScopeType.DIOCESE and not scope_diocese_id:
        raise ApplicationError("Un événement de portée 'diocèse' requiert un scope_id (diocèse).")
    if scope_type == Event.ScopeType.CHURCH and not scope_church_id:
        raise ApplicationError("Un événement de portée 'église' requiert un scope_church_id.")
    if scope_type == Event.ScopeType.GLOBAL and (
        scope_parish_id or scope_diocese_id or scope_church_id
    ):
        raise ApplicationError("Un événement global ne doit pas avoir de portée territoriale.")


def _check_event_scope_authority(
    *, user, scope_type, scope_parish_id, scope_diocese_id, scope_church_id
):
    """Autorité territoriale RÉELLE sur la portée (anti-injection). CHURCH suit la
    règle RG-CONT 3b : church_admin sur X OU autorité sur la paroisse de X."""
    from apps.agenda.models import Event
    from apps.users.scoping import (
        accessible_province_ids,
        is_global_admin,
        user_can_admin_church,
        user_can_admin_diocese,
        user_can_admin_parish,
    )

    if scope_type == Event.ScopeType.PARISH:
        if not user_can_admin_parish(user, scope_parish_id):
            raise ApplicationError("Vous n'avez pas autorité sur cette paroisse.")
    elif scope_type == Event.ScopeType.CHURCH:
        if not user_can_admin_church(user, scope_church_id):
            raise ApplicationError("Vous n'avez pas autorité sur cette église.")
    elif scope_type == Event.ScopeType.DIOCESE:
        if not user_can_admin_diocese(user, scope_diocese_id):
            raise ApplicationError("Vous n'avez pas autorité sur ce diocèse.")
    else:  # GLOBAL — réservé aux administrateurs province / national.
        if not (is_global_admin(user) or accessible_province_ids(user)):
            raise ApplicationError(
                "La portée globale est réservée aux administrateurs province ou national."
            )


def _resolve_event_scope_targets(*, scope_parish_id, scope_diocese_id, scope_church_id):
    from apps.org.models import Church, Diocese, Parish

    parish = diocese = church = None
    if scope_parish_id is not None:
        parish = Parish.objects.filter(pk=scope_parish_id).first()
        if parish is None:
            raise ApplicationError("Paroisse introuvable.")
    if scope_diocese_id is not None:
        diocese = Diocese.objects.filter(pk=scope_diocese_id).first()
        if diocese is None:
            raise ApplicationError("Diocèse introuvable.")
    if scope_church_id is not None:
        church = Church.objects.filter(pk=scope_church_id).first()
        if church is None:
            raise ApplicationError("Église introuvable.")
    return parish, diocese, church


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
    scope_church_id: int | None = None,
    max_participants: int | None = None,
):
    from apps.agenda.models import Event

    if not _can_create_event(organizer):
        raise ApplicationError("Seul le clergé ou les administrateurs peuvent créer des événements.")
    if end_at <= start_at:
        raise ApplicationError("La date de fin doit être après la date de début.")

    # Contrat d'entrée inchangé : le scope_id legacy (id unique) est désambiguïsé par
    # scope_type ; scope_church_id couvre la nouvelle portée église.
    scope_parish_id = scope_id if scope_type == Event.ScopeType.PARISH else None
    scope_diocese_id = scope_id if scope_type == Event.ScopeType.DIOCESE else None

    _check_event_scope_consistency(scope_type, scope_parish_id, scope_diocese_id, scope_church_id)
    _check_event_scope_authority(
        user=organizer,
        scope_type=scope_type,
        scope_parish_id=scope_parish_id,
        scope_diocese_id=scope_diocese_id,
        scope_church_id=scope_church_id,
    )
    parish, diocese, church = _resolve_event_scope_targets(
        scope_parish_id=scope_parish_id,
        scope_diocese_id=scope_diocese_id,
        scope_church_id=scope_church_id,
    )

    return Event.objects.create(
        organizer=organizer,
        title=title,
        description=description,
        event_type=event_type,
        start_at=start_at,
        end_at=end_at,
        location=location,
        scope_type=scope_type,
        scope_parish=parish,
        scope_diocese=diocese,
        scope_church=church,
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

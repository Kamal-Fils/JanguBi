from functools import partial

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import ApplicationError
from apps.users.enums import CLERGY_PASTORAL_ROLES, PastoralRole

# Rôles pastoraux qui ORGANISENT un événement (matrice §16 — AGENDA « Créer
# événement ») : diacre/prêtre au niveau paroisse, évêque au diocèse, archevêque
# à la province. Le religieux, présent dans CLERGY_PASTORAL_ROLES, n'organise pas.
_PASTORAL_ORGANIZER_ROLES = frozenset({
    PastoralRole.DIACRE,
    PastoralRole.PRETRE,
    PastoralRole.EVEQUE,
    PastoralRole.ARCHEVEQUE,
})


def _can_create_event(user) -> bool:
    """Filtre d'entrée (« qui peut organiser »). L'autorité TERRITORIALE fine est
    tranchée ensuite par ``_check_event_scope_authority``."""
    from apps.users.scoping import is_any_admin

    return getattr(user, "pastoral_role", None) in CLERGY_PASTORAL_ROLES or is_any_admin(user)


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
    règle RG-CONT 3b : church_admin sur X OU autorité sur la paroisse de X.

    Deux voies indépendantes : la capacité ADMIN (``RoleAssignment``) et le rôle
    PASTORAL (``user_has_pastoral_authority``, module canonique du cloisonnement
    ``apps.users.scoping``). L'une suffit."""
    from apps.agenda.models import Event
    from apps.users.scoping import (
        accessible_province_ids,
        is_global_admin,
        user_can_admin_church,
        user_can_admin_diocese,
        user_can_admin_parish,
        user_has_pastoral_authority,
    )

    if user_has_pastoral_authority(
        user=user,
        scope_type=scope_type,
        scope_parish_id=scope_parish_id,
        scope_diocese_id=scope_diocese_id,
        scope_church_id=scope_church_id,
        allowed_roles=_PASTORAL_ORGANIZER_ROLES,
    ):
        return

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


def can_manage_event(*, user, event) -> bool:
    """Peut annuler l'événement : son organisateur, ou une autorité (pastorale ou
    administrative) sur SA portée — mêmes règles que la création."""
    if event.organizer_id is not None and event.organizer_id == user.id:
        return True
    try:
        _check_event_scope_authority(
            user=user,
            scope_type=event.scope_type,
            scope_parish_id=event.scope_parish_id,
            scope_diocese_id=event.scope_diocese_id,
            scope_church_id=event.scope_church_id,
        )
    except ApplicationError:
        return False
    return True


def _notify_registrants_of_cancellation(*, event) -> None:
    """Prévient chaque inscrit via le pipeline Email + Celery (jamais de SMTP
    direct) : l'envoi est dispatché après COMMIT de l'annulation."""
    from apps.emails.models import Email
    from apps.emails.tasks import email_send as email_send_task

    subject = f"[Jàngu Bi] Événement annulé — {event.title}"
    html = (
        f"<p>Bonjour,</p>"
        f"<p>L'événement <strong>{event.title}</strong> prévu le "
        f"{event.start_at:%d/%m/%Y à %H:%M} a été annulé.</p>"
        f"<p>Votre inscription est donc sans objet. Nous vous prions de nous "
        f"excuser pour ce contretemps.</p>"
    )

    # bulk_create : un seul INSERT, sinon un événement à N inscrits tiendrait la
    # transaction ouverte pendant N allers-retours.
    emails = Email.objects.bulk_create(
        [
            Email(
                to=registration.user.email,
                subject=subject,
                html=html,
                plain_text=html,
                status=Email.Status.SENDING,
            )
            for registration in event.registrations.select_related("user")
            if registration.user.email
        ]
    )
    for email in emails:
        # partial (et non lambda) : lie la valeur de l'itération sans capturer la
        # variable de boucle — chaque email est bien dispatché avec son propre id.
        transaction.on_commit(partial(email_send_task.delay, email.id))


@transaction.atomic
def event_cancel(*, event, actor):
    """Annulation DOUCE d'un événement (la « suppression » exposée par l'API).

    On ne détruit pas la ligne : ``EventRegistration.event`` est en CASCADE, donc
    un DELETE sec effacerait sans trace l'engagement des fidèles inscrits. On
    horodate l'annulation, on sort l'événement des feeds, on ferme les nouvelles
    inscriptions, et on prévient les inscrits.

    L'autorité est vérifiée ICI, et pas seulement dans la vue : le service reste
    la couche qui garantit ses propres invariants, quel que soit l'appelant
    (tâche Celery, commande d'administration, autre service).
    """
    if not can_manage_event(user=actor, event=event):
        raise ApplicationError(
            "Seul l'organisateur ou une autorité sur cet événement peut l'annuler."
        )
    if event.cancelled_at is not None:
        raise ApplicationError("Cet événement est déjà annulé.")

    event.cancelled_at = timezone.now()
    event.cancelled_by = actor
    event.save(update_fields=["cancelled_at", "cancelled_by", "updated_at"])

    _notify_registrants_of_cancellation(event=event)
    return event


@transaction.atomic
def event_register(*, event, user):
    """Inscription à un événement, sous VERROU de la ligne événement.

    ``max_participants`` est une jauge « lire puis écrire » : sans verrou, deux
    inscriptions concurrentes sur la dernière place lisent toutes deux
    ``count < max``, puis insèrent toutes deux — la jauge est franchie en silence
    (TOCTOU). On relit donc l'événement en ``SELECT ... FOR UPDATE`` : la seconde
    transaction attend la première, recompte, et voit l'événement complet.

    Verrou plutôt que contrainte en base : PostgreSQL ne sait pas exprimer
    « COUNT(registrations) <= event.max_participants » dans un CHECK (agrégat
    inter-tables) ; il faudrait un TRIGGER ou un compteur dénormalisé à maintenir
    en cohérence — deux sources de vérité pour la même quantité. Le verrou ne
    porte que sur UN événement et l'inscription est une écriture rare : la
    contention est négligeable.

    On lit aussi ``cancelled_at`` sur la ligne VERROUILLÉE, et non sur l'instance
    reçue : celle-ci peut avoir été chargée avant une annulation déjà committée.
    """
    from apps.agenda.models import Event, EventRegistration

    locked_event = Event.objects.select_for_update().filter(pk=event.pk).first()
    if locked_event is None:
        raise ApplicationError("Événement introuvable.")
    if locked_event.cancelled_at is not None:
        raise ApplicationError("Cet événement a été annulé.")
    if locked_event.max_participants is not None:
        count = EventRegistration.objects.filter(event_id=locked_event.pk).count()
        if count >= locked_event.max_participants:
            raise ApplicationError("Cet événement est complet.")

    registration, created = EventRegistration.objects.get_or_create(
        event=locked_event, user=user
    )
    if not created:
        raise ApplicationError("Vous êtes déjà inscrit à cet événement.")
    return registration


@transaction.atomic
def event_unregister(*, event, user) -> None:
    from apps.agenda.models import EventRegistration

    deleted, _ = EventRegistration.objects.filter(event=event, user=user).delete()
    if not deleted:
        raise ApplicationError("Vous n'êtes pas inscrit à cet événement.")

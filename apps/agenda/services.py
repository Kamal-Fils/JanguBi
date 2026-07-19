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
# Rôles dont l'autorité pastorale porte au-delà de la paroisse.
_PASTORAL_DIOCESAN_ROLES = frozenset({PastoralRole.EVEQUE, PastoralRole.ARCHEVEQUE})


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


def _pastoral_diocese_ids(user, *, membership_diocese_ids: set[int]) -> set[int]:
    """Diocèses couverts par le rôle PASTORAL : l'évêque couvre le sien,
    l'archevêque toute sa province. Dérivé de SON rattachement, jamais d'une
    donnée du client.

    On part des diocèses issus des appartenances (requête fraîche) plutôt que du
    seul ``user.diocese_id`` : cette colonne est dénormalisée par signal via
    ``.update()``, donc une instance ``BaseUser`` déjà chargée peut la porter
    périmée. Elle reste prise en compte, en complément.
    """
    from apps.org.models import Diocese

    role = getattr(user, "pastoral_role", None)
    if role not in _PASTORAL_DIOCESAN_ROLES:
        return set()

    diocese_ids = set(membership_diocese_ids)
    if user.diocese_id:
        diocese_ids.add(user.diocese_id)

    if role == PastoralRole.ARCHEVEQUE:
        province_ids = {
            pid
            for pid in Diocese.objects.filter(id__in=diocese_ids).values_list(
                "province_id", flat=True
            )
            if pid is not None
        }
        if user.province_id:
            province_ids.add(user.province_id)
        if province_ids:
            diocese_ids |= set(
                Diocese.objects.filter(province_id__in=province_ids).values_list("id", flat=True)
            )
    return diocese_ids


def _has_pastoral_authority(
    *, user, scope_type, scope_parish_id, scope_diocese_id, scope_church_id
) -> bool:
    """Autorité issue du rôle PASTORAL, orthogonale à la dimension admin
    (``UserRole`` / ``RoleAssignment``) : un curé porte ``pastoral_role=PRETRE``
    sans forcément de capacité administrative (cf. ``clergy_accounts
    ._resolve_capacity`` : « sans cible exploitable, aucune affectation scopée
    n'est créée »). Il reste pourtant l'acteur naturel d'un événement paroissial.

    FAIL-CLOSED : la portée demandée doit tomber dans le territoire d'appartenance
    RÉEL de l'utilisateur (``Membership`` → get_scope_ids, diocèse/province
    dérivés). Un identifiant arbitraire venu du client n'ouvre jamais de droit, et
    la portée GLOBAL n'est jamais accordée par cette voie.
    """
    from apps.agenda.models import Event
    from apps.org.models import Church, Parish

    if getattr(user, "pastoral_role", None) not in _PASTORAL_ORGANIZER_ROLES:
        return False

    scope = user.get_scope_ids()
    parish_ids = set(scope["parish_ids"])
    church_ids = set(scope["church_ids"])
    diocese_ids = _pastoral_diocese_ids(
        user, membership_diocese_ids=set(scope["diocese_ids"])
    )

    if scope_type == Event.ScopeType.PARISH:
        if scope_parish_id is None:
            return False
        if scope_parish_id in parish_ids:
            return True
        return bool(diocese_ids) and Parish.objects.filter(
            pk=scope_parish_id, diocese_id__in=diocese_ids
        ).exists()

    if scope_type == Event.ScopeType.CHURCH:
        if scope_church_id is None:
            return False
        if scope_church_id in church_ids:
            return True
        # Toute église de sa paroisse (curé) ou de son diocèse (évêque).
        qs = Church.objects.filter(pk=scope_church_id)
        if parish_ids and qs.filter(parish_id__in=parish_ids).exists():
            return True
        return bool(diocese_ids) and qs.filter(parish__diocese_id__in=diocese_ids).exists()

    if scope_type == Event.ScopeType.DIOCESE:
        return scope_diocese_id is not None and scope_diocese_id in diocese_ids

    # GLOBAL : réservé aux administrateurs province / national.
    return False


def _check_event_scope_authority(
    *, user, scope_type, scope_parish_id, scope_diocese_id, scope_church_id
):
    """Autorité territoriale RÉELLE sur la portée (anti-injection). CHURCH suit la
    règle RG-CONT 3b : church_admin sur X OU autorité sur la paroisse de X.

    Deux voies indépendantes : la capacité ADMIN (``RoleAssignment``) et le rôle
    PASTORAL (voir ``_has_pastoral_authority``). L'une suffit."""
    from apps.agenda.models import Event
    from apps.users.scoping import (
        accessible_province_ids,
        is_global_admin,
        user_can_admin_church,
        user_can_admin_diocese,
        user_can_admin_parish,
    )

    if _has_pastoral_authority(
        user=user,
        scope_type=scope_type,
        scope_parish_id=scope_parish_id,
        scope_diocese_id=scope_diocese_id,
        scope_church_id=scope_church_id,
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
    from apps.agenda.models import EventRegistration

    if event.cancelled_at is not None:
        raise ApplicationError("Cet événement a été annulé.")
    if event.max_participants is not None:
        count = event.registrations.count()
        if count >= event.max_participants:
            raise ApplicationError("Cet événement est complet.")
    registration, created = EventRegistration.objects.get_or_create(event=event, user=user)
    if not created:
        raise ApplicationError("Vous êtes déjà inscrit à cet événement.")
    return registration


@transaction.atomic
def event_unregister(*, event, user) -> None:
    from apps.agenda.models import EventRegistration

    deleted, _ = EventRegistration.objects.filter(event=event, user=user).delete()
    if not deleted:
        raise ApplicationError("Vous n'êtes pas inscrit à cet événement.")

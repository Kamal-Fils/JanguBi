from django.db import transaction

from apps.core.exceptions import ApplicationError

from .models import MassIntention, MassIntentionStatus


@transaction.atomic
def mass_intention_submit(
    *,
    requestor,
    intention_type: str,
    intention_text: str,
    parish=None,
) -> MassIntention:
    # B6b : défaut = paroisse PRINCIPALE du demandeur (appartenance is_primary),
    # repli legacy sur primary_parish ; jamais None.
    if parish is None:
        from apps.users.models import Membership

        primary = (
            Membership.objects.filter(user=requestor, is_primary=True)
            .select_related("church__parish")
            .first()
        )
        if primary is not None:
            parish = primary.church.parish
        else:
            parish = getattr(getattr(requestor, "profile", None), "primary_parish", None)
    if parish is None:
        raise ApplicationError(
            "Aucune paroisse : précisez la paroisse ou définissez votre paroisse principale."
        )

    intention = MassIntention.objects.create(
        requestor=requestor,
        intention_type=intention_type,
        intention_text=intention_text,
        parish=parish,
    )
    return intention


def _assert_parish_authority(*, intention: MassIntention, pretre) -> None:
    """Garde territoriale des actions de traitement (RG-SEC).

    Le contrôle de rôle fait en amont dans ``apis.py`` est **global** : il dit
    « c'est un prêtre », pas « c'est LE prêtre de cette paroisse ». Sans cette
    garde, n'importe quel prêtre du pays pouvait accepter/refuser/dater/célébrer
    l'intention d'un fidèle d'une autre paroisse — et lire au passage
    ``intention_text``, qui contient souvent une confidence personnelle.

    On lève une ``ApplicationError`` (et non ``Http404``) parce qu'on est dans
    la couche service : elle doit rester sûre même appelée hors HTTP (tâche
    Celery, commande de gestion, futur endpoint) et ne doit pas connaître les
    exceptions HTTP. Le non-dévoilement d'existence est déjà assuré en amont
    par ``mass_intention_get``, qui lève ``Http404``.

    Fail-closed : périmètre vide, ou intention sans paroisse, → refus (sauf
    admin global). Le message ne nomme jamais la paroisse d'autrui.
    """
    from .selectors import pretre_accessible_parish_ids

    parish_ids = pretre_accessible_parish_ids(user=pretre)
    if parish_ids is None:  # admin global — autorité sur tout le territoire
        return
    if intention.parish_id is None or intention.parish_id not in parish_ids:
        raise ApplicationError("Vous n'avez pas autorité sur la paroisse de cette intention.")


@transaction.atomic
def mass_intention_accept(*, intention: MassIntention, pretre) -> MassIntention:
    _assert_parish_authority(intention=intention, pretre=pretre)
    if intention.status != MassIntentionStatus.PENDING:
        raise ApplicationError("Cette intention n'est pas en attente d'acceptation.")
    intention.pretre = pretre
    intention.status = MassIntentionStatus.ACCEPTED
    intention.save(update_fields=["pretre", "status", "updated_at"])
    return intention


@transaction.atomic
def mass_intention_propose_date(
    *, intention: MassIntention, proposed_date, pretre
) -> MassIntention:
    _assert_parish_authority(intention=intention, pretre=pretre)
    if intention.status not in (MassIntentionStatus.ACCEPTED, MassIntentionStatus.CONFIRMED):
        raise ApplicationError("Cette intention doit être acceptée avant de proposer une date.")
    intention.proposed_date = proposed_date
    intention.status = MassIntentionStatus.DATE_PROPOSED
    intention.save(update_fields=["proposed_date", "status", "updated_at"])
    return intention


@transaction.atomic
def mass_intention_celebrate(*, intention: MassIntention, pretre) -> MassIntention:
    _assert_parish_authority(intention=intention, pretre=pretre)
    if intention.status not in (
        MassIntentionStatus.ACCEPTED,
        MassIntentionStatus.DATE_PROPOSED,
        MassIntentionStatus.CONFIRMED,
    ):
        raise ApplicationError("Cette intention n'est pas dans un état permettant la célébration.")
    intention.status = MassIntentionStatus.CELEBRATED
    intention.save(update_fields=["status", "updated_at"])
    return intention


@transaction.atomic
def mass_intention_decline(
    *, intention: MassIntention, pretre, notes: str = ""
) -> MassIntention:
    _assert_parish_authority(intention=intention, pretre=pretre)
    if intention.status not in (MassIntentionStatus.PENDING, MassIntentionStatus.ACCEPTED):
        raise ApplicationError("Cette intention ne peut pas être refusée dans son état actuel.")
    intention.status = MassIntentionStatus.DECLINED
    intention.notes = notes
    intention.save(update_fields=["status", "notes", "updated_at"])
    return intention

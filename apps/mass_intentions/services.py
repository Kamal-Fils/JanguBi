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


@transaction.atomic
def mass_intention_accept(*, intention: MassIntention, pretre) -> MassIntention:
    if intention.status != MassIntentionStatus.PENDING:
        raise ApplicationError("Cette intention n'est pas en attente d'acceptation.")
    intention.pretre = pretre
    intention.status = MassIntentionStatus.ACCEPTED
    intention.save(update_fields=["pretre", "status", "updated_at"])
    return intention


@transaction.atomic
def mass_intention_propose_date(*, intention: MassIntention, proposed_date) -> MassIntention:
    if intention.status not in (MassIntentionStatus.ACCEPTED, MassIntentionStatus.CONFIRMED):
        raise ApplicationError("Cette intention doit être acceptée avant de proposer une date.")
    intention.proposed_date = proposed_date
    intention.status = MassIntentionStatus.DATE_PROPOSED
    intention.save(update_fields=["proposed_date", "status", "updated_at"])
    return intention


@transaction.atomic
def mass_intention_celebrate(*, intention: MassIntention) -> MassIntention:
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
def mass_intention_decline(*, intention: MassIntention, notes: str = "") -> MassIntention:
    if intention.status not in (MassIntentionStatus.PENDING, MassIntentionStatus.ACCEPTED):
        raise ApplicationError("Cette intention ne peut pas être refusée dans son état actuel.")
    intention.status = MassIntentionStatus.DECLINED
    intention.notes = notes
    intention.save(update_fields=["status", "notes", "updated_at"])
    return intention

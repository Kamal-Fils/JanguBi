from django.db import transaction

from apps.core.exceptions import ApplicationError

from .models import ParishTransferRequest, TransferStatus

# États non terminaux : un demandeur ne peut avoir qu'UNE demande active à la fois.
_ACTIVE_STATUSES = (
    TransferStatus.PENDING,
    TransferStatus.APPROVED_BY_ORIGIN,
    TransferStatus.ACKNOWLEDGED_BY_DESTINATION,
)


def _requester_origin_parish(requester):
    """Paroisse d'origine = paroisse de l'appartenance PRINCIPALE du demandeur,
    avec repli legacy sur ``Profile.primary_parish``. Peut être None (fidèle non
    rattaché)."""
    from apps.users.models import Membership

    primary = (
        Membership.objects.filter(user=requester, is_primary=True)
        .select_related("church__parish")
        .first()
    )
    if primary is not None:
        return primary.church.parish
    return getattr(getattr(requester, "profile", None), "primary_parish", None)


@transaction.atomic
def transfer_create(
    *,
    requester,
    destination_parish,
    reason: str = "",
) -> ParishTransferRequest:
    if destination_parish is None:
        raise ApplicationError("La paroisse de destination est requise.")

    if (
        ParishTransferRequest.objects.filter(requester=requester)
        .filter(status__in=_ACTIVE_STATUSES)
        .exists()
    ):
        raise ApplicationError("Vous avez déjà une demande de transfert en cours.")

    origin_parish = _requester_origin_parish(requester)
    if origin_parish is not None and origin_parish.pk == destination_parish.pk:
        raise ApplicationError(
            "La paroisse de destination doit être différente de votre paroisse actuelle."
        )

    transfer = ParishTransferRequest.objects.create(
        requester=requester,
        origin_parish=origin_parish,
        destination_parish=destination_parish,
        reason=reason or "",
    )
    return transfer


@transaction.atomic
def transfer_approve(*, transfer: ParishTransferRequest) -> ParishTransferRequest:
    if transfer.status != TransferStatus.PENDING:
        raise ApplicationError("Cette demande n'est pas en attente d'approbation.")
    transfer.status = TransferStatus.APPROVED_BY_ORIGIN
    transfer.save(update_fields=["status", "updated_at"])
    return transfer


@transaction.atomic
def transfer_reject(*, transfer: ParishTransferRequest, reason: str) -> ParishTransferRequest:
    if transfer.status not in (
        TransferStatus.PENDING,
        TransferStatus.APPROVED_BY_ORIGIN,
    ):
        raise ApplicationError("Cette demande ne peut plus être rejetée dans son état actuel.")
    if not reason:
        raise ApplicationError("Un motif de rejet est requis.")
    transfer.status = TransferStatus.REJECTED
    transfer.rejection_reason = reason
    transfer.save(update_fields=["status", "rejection_reason", "updated_at"])
    return transfer


@transaction.atomic
def transfer_acknowledge(*, transfer: ParishTransferRequest) -> ParishTransferRequest:
    """Finalise le transfert : la paroisse de destination accuse réception.

    Déplace l'appartenance PRINCIPALE du demandeur vers la paroisse de destination
    via le mécanisme réel des appartenances (``services_memberships``). La création /
    promotion d'une ``Membership`` principale déclenche le signal
    ``sync_hierarchy_from_membership`` qui met à jour ``BaseUser.diocese`` /
    ``province`` ET, en miroir transitoire, ``Profile.primary_parish``.
    """
    if transfer.status != TransferStatus.APPROVED_BY_ORIGIN:
        raise ApplicationError(
            "La demande doit être approuvée par la paroisse d'origine avant finalisation."
        )

    destination_parish = transfer.destination_parish
    if destination_parish is None:
        raise ApplicationError("La paroisse de destination est introuvable.")

    _move_requester_to_parish(requester=transfer.requester, parish=destination_parish)

    transfer.status = TransferStatus.COMPLETED
    transfer.save(update_fields=["status", "updated_at"])
    return transfer


def _move_requester_to_parish(*, requester, parish) -> None:
    """Rattache (en principal) le demandeur à l'église principale de ``parish``.

    Utilise les services d'appartenance : ``membership_set_primary`` si une
    appartenance à cette église existe déjà, sinon ``membership_create`` (qui
    démote l'ancienne principale et termine l'onboarding). Le signal
    ``Membership`` propage diocèse/province/primary_parish."""
    from apps.org.models import Church
    from apps.users.models import Membership
    from apps.users.services_memberships import membership_create, membership_set_primary

    church = (
        Church.objects.filter(parish=parish, is_main=True).first()
        or Church.objects.filter(parish=parish).order_by("created_at", "pk").first()
    )
    if church is None:
        raise ApplicationError(
            "La paroisse de destination ne dispose d'aucune église : transfert impossible."
        )

    existing = Membership.objects.filter(user=requester, church=church).first()
    if existing is not None:
        membership_set_primary(user=requester, membership=existing)
    else:
        membership_create(user=requester, church=church, is_primary=True)

from django.db.models import Q, QuerySet

from apps.core.exceptions import ApplicationError

from .models import ParishTransferRequest


def transfer_get_my(*, requester) -> ParishTransferRequest:
    """Demande de transfert courante / la plus récente du demandeur.

    Lève ``ApplicationError`` si le demandeur n'a aucune demande (l'API mappe en
    404 : le front traite 404 comme « aucune demande »)."""
    transfer = (
        ParishTransferRequest.objects.filter(requester=requester)
        .select_related("origin_parish", "destination_parish")
        .order_by("-created_at")
        .first()
    )
    if transfer is None:
        raise ApplicationError("Aucune demande de transfert.")
    return transfer


def transfer_list_for_admin(*, user) -> QuerySet[ParishTransferRequest]:
    """Transferts concernant les paroisses administrées par ``user`` (origine OU
    destination). Source de vérité d'autorité = ``RoleAssignment`` via le scoping.
    Fail-CLOSED : un admin sans affectation territoriale ne voit rien."""
    from apps.users.scoping import accessible_parish_ids, is_global_admin

    qs = ParishTransferRequest.objects.select_related(
        "requester", "origin_parish", "destination_parish"
    )

    if is_global_admin(user):
        return qs.order_by("-created_at")

    parish_ids = accessible_parish_ids(user)  # set (jamais None ici)
    qs = qs.filter(
        Q(origin_parish_id__in=parish_ids) | Q(destination_parish_id__in=parish_ids)
    )
    return qs.order_by("-created_at")


def transfer_get_by_id(*, transfer_id: int) -> ParishTransferRequest:
    try:
        return ParishTransferRequest.objects.select_related(
            "requester", "origin_parish", "destination_parish"
        ).get(id=transfer_id)
    except ParishTransferRequest.DoesNotExist:
        raise ApplicationError(f"Demande de transfert {transfer_id} introuvable.")

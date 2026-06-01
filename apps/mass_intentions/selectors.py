from django.db.models import QuerySet

from .models import MassIntention


def mass_intention_list_for_requestor(*, requestor) -> QuerySet[MassIntention]:
    return MassIntention.objects.filter(requestor=requestor).select_related("pretre", "parish")


def mass_intention_list_for_parish(*, parish_id: int) -> QuerySet[MassIntention]:
    return MassIntention.objects.filter(parish_id=parish_id).select_related(
        "requestor", "pretre", "parish"
    )


def mass_intention_list_pending(*, pretre=None) -> QuerySet[MassIntention]:
    qs = MassIntention.objects.filter(status="pending").select_related(
        "requestor", "pretre", "parish"
    )
    if pretre is not None:
        # Bug corrigé : primary_parish vit sur Profile, pas sur BaseUser.
        profile = getattr(pretre, "profile", None)
        primary_parish_id = getattr(profile, "primary_parish_id", None)
        if primary_parish_id:
            qs = qs.filter(parish_id=primary_parish_id)
    return qs


def mass_intention_get(*, intention_id: int) -> MassIntention:
    from apps.core.exceptions import ApplicationError

    try:
        return MassIntention.objects.select_related("requestor", "pretre", "parish").get(
            id=intention_id
        )
    except MassIntention.DoesNotExist:
        raise ApplicationError(f"Intention {intention_id} introuvable.")

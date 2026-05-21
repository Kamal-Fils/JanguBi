from django.db.models import QuerySet

from apps.org.models import Diocese, Parish, Province, ReligiousCommunity


def province_list() -> QuerySet[Province]:
    return Province.objects.all().order_by("name")


def diocese_list(*, province_id: int | None = None) -> QuerySet[Diocese]:
    qs = Diocese.objects.select_related("province")
    if province_id is not None:
        qs = qs.filter(province_id=province_id)
    return qs.order_by("name")


def parish_list(*, diocese_id: int | None = None, search: str | None = None) -> QuerySet[Parish]:
    qs = Parish.objects.select_related("diocese__province")
    if diocese_id is not None:
        qs = qs.filter(diocese_id=diocese_id)
    if search:
        qs = qs.filter(name__icontains=search) | qs.filter(city__icontains=search)
        qs = qs.distinct()
    return qs.order_by("name")


def parish_get_by_id(*, parish_id: int) -> Parish:
    from apps.core.exceptions import ApplicationError

    try:
        return Parish.objects.select_related("diocese__province").get(id=parish_id)
    except Parish.DoesNotExist:
        raise ApplicationError(f"Paroisse {parish_id} introuvable.")


def religious_community_list(*, diocese_id: int | None = None) -> QuerySet[ReligiousCommunity]:
    qs = ReligiousCommunity.objects.select_related("order", "diocese", "parish")
    if diocese_id is not None:
        qs = qs.filter(diocese_id=diocese_id)
    return qs.order_by("name")

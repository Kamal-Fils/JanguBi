from django.db.models import QuerySet

from apps.org.models import Church, Deanery, Diocese, Parish, Province, ReligiousCommunity


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


# ---------------------------------------------------------------------------
# Églises & doyennés
# ---------------------------------------------------------------------------

def church_list(*, parish_id: int | None = None) -> QuerySet[Church]:
    qs = Church.objects.select_related("parish__diocese")
    if parish_id is not None:
        qs = qs.filter(parish_id=parish_id)
    return qs.order_by("parish__name", "-is_main", "name")


def church_get_by_id(*, church_id: int) -> Church:
    from apps.core.exceptions import ApplicationError

    try:
        return Church.objects.select_related("parish__diocese__province").get(id=church_id)
    except Church.DoesNotExist:
        raise ApplicationError(f"Église {church_id} introuvable.")


def parish_main_church(*, parish_id: int) -> Church | None:
    return Church.objects.filter(parish_id=parish_id, is_main=True).first()


def deanery_list(*, diocese_id: int | None = None) -> QuerySet[Deanery]:
    qs = Deanery.objects.select_related("diocese", "dean")
    if diocese_id is not None:
        qs = qs.filter(diocese_id=diocese_id)
    return qs.order_by("name")

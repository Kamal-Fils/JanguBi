from django.db import transaction

from apps.core.exceptions import ApplicationError
from apps.org.enums import ChurchType
from apps.org.models import (
    Church,
    Deanery,
    Diocese,
    Parish,
    Province,
)


@transaction.atomic
def province_create(*, name: str, code: str, country: str = "Senegal") -> Province:
    if Province.objects.filter(code=code).exists():
        raise ApplicationError(f"Une province avec le code '{code}' existe déjà.")
    return Province.objects.create(name=name, code=code, country=country)


@transaction.atomic
def province_update(*, province: Province, name: str | None = None, code: str | None = None) -> Province:
    if name is not None:
        province.name = name
    if code is not None:
        if Province.objects.exclude(pk=province.pk).filter(code=code).exists():
            raise ApplicationError(f"Le code '{code}' est déjà utilisé.")
        province.code = code
    province.full_clean()
    province.save(update_fields=["name", "code", "updated_at"])
    return province


@transaction.atomic
def province_delete(*, province: Province) -> None:
    """Supprime une province — refusée si des enfants ou des données « vivantes »
    la référencent (même philosophie que ``parish_delete`` : aucune cascade sur
    des données utilisateur). Les diocèses rattachés bloquent ; les affectations
    actives (``RoleAssignment.province`` est CASCADE) bloquent aussi. Toute FK
    PROTECT résiduelle est convertie en erreur métier claire.
    """
    from django.db.models import ProtectedError

    from apps.users.models import RoleAssignment

    if province.dioceses.exists():
        raise ApplicationError(
            "Impossible de supprimer une province ayant des diocèses rattachés."
        )
    if RoleAssignment.objects.filter(province=province, is_active=True).exists():
        raise ApplicationError(
            "Impossible de supprimer une province ayant des affectations actives."
        )
    try:
        province.delete()
    except ProtectedError:
        raise ApplicationError(
            "Impossible de supprimer cette province : des données la référencent."
        )


@transaction.atomic
def diocese_create(*, name: str, code: str, province: Province) -> Diocese:
    if Diocese.objects.filter(code=code).exists():
        raise ApplicationError(f"Un diocèse avec le code '{code}' existe déjà.")
    return Diocese.objects.create(name=name, code=code, province=province)


@transaction.atomic
def diocese_update(*, diocese: Diocese, name: str | None = None, code: str | None = None) -> Diocese:
    if name is not None:
        diocese.name = name
    if code is not None:
        if Diocese.objects.exclude(pk=diocese.pk).filter(code=code).exists():
            raise ApplicationError(f"Le code '{code}' est déjà utilisé.")
        diocese.code = code
    diocese.full_clean()
    diocese.save(update_fields=["name", "code", "updated_at"])
    return diocese


@transaction.atomic
def diocese_delete(*, diocese: Diocese) -> None:
    """Supprime un diocèse — refusée si des enfants ou des données « vivantes »
    le référencent (même philosophie que ``parish_delete``). Paroisses, doyennés
    et communautés religieuses rattachés bloquent ; les affectations actives
    (``RoleAssignment.diocese`` est CASCADE) bloquent aussi. Toute FK PROTECT
    résiduelle est convertie en erreur métier claire.
    """
    from django.db.models import ProtectedError

    from apps.users.models import RoleAssignment

    if diocese.parishes.exists():
        raise ApplicationError(
            "Impossible de supprimer un diocèse ayant des paroisses rattachées."
        )
    if diocese.deaneries.exists():
        raise ApplicationError(
            "Impossible de supprimer un diocèse ayant des doyennés rattachés."
        )
    if diocese.communities.exists():
        raise ApplicationError(
            "Impossible de supprimer un diocèse ayant des communautés religieuses rattachées."
        )
    if RoleAssignment.objects.filter(diocese=diocese, is_active=True).exists():
        raise ApplicationError(
            "Impossible de supprimer un diocèse ayant des affectations actives."
        )
    try:
        diocese.delete()
    except ProtectedError:
        raise ApplicationError(
            "Impossible de supprimer ce diocèse : des données le référencent."
        )


@transaction.atomic
def parish_create(*, name: str, diocese: Diocese, city: str = "", address: str = "") -> Parish:
    parish = Parish.objects.create(name=name, diocese=diocese, city=city, address=address)
    # RG-ORG-04 : toute paroisse possède au minimum son église paroissiale principale.
    Church.objects.create(
        parish=parish,
        name=name,
        church_type=ChurchType.PAROISSIALE,
        is_main=True,
        city=city,
        address=address,
    )
    return parish


@transaction.atomic
def parish_update(
    *,
    parish: Parish,
    name: str | None = None,
    city: str | None = None,
    address: str | None = None,
) -> Parish:
    if name is not None:
        parish.name = name
    if city is not None:
        parish.city = city
    if address is not None:
        parish.address = address
    parish.full_clean()
    parish.save(update_fields=["name", "city", "address", "updated_at"])
    return parish


@transaction.atomic
def parish_delete(*, parish: Parish) -> None:
    """Supprime une paroisse — refusée si des données « vivantes » la référencent.

    Garde-fous d'intégrité (aucune suppression en cascade de données utilisateur) :
    appartenances et affectations actives bloquent. Sinon on retire les églises de
    la paroisse (dont la principale auto-créée) puis la paroisse ; toute FK PROTECT
    résiduelle (dons, événements, documents…) est convertie en erreur métier claire.
    """
    from django.db.models import ProtectedError

    from apps.users.models import Membership, RoleAssignment

    if Membership.objects.filter(church__parish=parish).exists():
        raise ApplicationError(
            "Impossible de supprimer une paroisse ayant des appartenances."
        )
    if RoleAssignment.objects.filter(parish=parish, is_active=True).exists():
        raise ApplicationError(
            "Impossible de supprimer une paroisse ayant des affectations actives."
        )
    try:
        Church.objects.filter(parish=parish).delete()
        parish.delete()
    except ProtectedError:
        raise ApplicationError(
            "Impossible de supprimer cette paroisse : des données la référencent "
            "(dons, événements, documents…)."
        )


# ---------------------------------------------------------------------------
# Églises
# ---------------------------------------------------------------------------

@transaction.atomic
def church_create(
    *,
    parish: Parish,
    name: str,
    church_type: str = ChurchType.SUCCURSALE,
    is_main: bool = False,
    city: str = "",
    address: str = "",
    latitude=None,
    longitude=None,
) -> Church:
    make_main = bool(is_main) or church_type == ChurchType.PAROISSIALE
    if make_main:
        church_type = ChurchType.PAROISSIALE
        # Démote l'église principale existante pour respecter `unique_main_church_per_parish`.
        Church.objects.filter(parish=parish, is_main=True).update(is_main=False)
    return Church.objects.create(
        parish=parish,
        name=name,
        church_type=church_type,
        is_main=make_main,
        city=city,
        address=address,
        latitude=latitude,
        longitude=longitude,
    )


@transaction.atomic
def church_set_main(*, church: Church) -> Church:
    Church.objects.filter(parish_id=church.parish_id, is_main=True).exclude(pk=church.pk).update(
        is_main=False
    )
    church.is_main = True
    church.church_type = ChurchType.PAROISSIALE
    church.save(update_fields=["is_main", "church_type", "updated_at"])
    return church


@transaction.atomic
def church_update(
    *,
    church: Church,
    name: str | None = None,
    church_type: str | None = None,
    city: str | None = None,
    address: str | None = None,
    is_active: bool | None = None,
) -> Church:
    if name is not None:
        church.name = name
    # Le type d'une église principale reste PAROISSIALE (cohérence canonique).
    if church_type is not None and not church.is_main:
        church.church_type = church_type
    if city is not None:
        church.city = city
    if address is not None:
        church.address = address
    if is_active is not None:
        church.is_active = is_active
    church.save()
    return church


@transaction.atomic
def church_delete(*, church: Church) -> None:
    """Supprime une église — refusée si des données « vivantes » la référencent
    (même philosophie que ``parish_delete`` : aucune cascade sur des données
    utilisateur). Les appartenances (``Membership.church`` est CASCADE) et les
    affectations actives (``RoleAssignment.church`` est CASCADE) bloquent.
    L'église principale n'est pas supprimable tant que la paroisse possède
    d'autres églises : en désigner une autre d'abord via ``church_set_main``.
    Toute FK PROTECT résiduelle est convertie en erreur métier claire.
    """
    from django.db.models import ProtectedError

    from apps.users.models import Membership, RoleAssignment

    if Membership.objects.filter(church=church).exists():
        raise ApplicationError(
            "Impossible de supprimer une église ayant des appartenances."
        )
    if RoleAssignment.objects.filter(church=church, is_active=True).exists():
        raise ApplicationError(
            "Impossible de supprimer une église ayant des affectations actives."
        )
    if church.is_main and Church.objects.filter(parish_id=church.parish_id).exclude(pk=church.pk).exists():
        raise ApplicationError(
            "Impossible de supprimer l'église principale : désignez d'abord "
            "une autre église principale."
        )
    try:
        church.delete()
    except ProtectedError:
        raise ApplicationError(
            "Impossible de supprimer cette église : des données la référencent."
        )


# ---------------------------------------------------------------------------
# Doyennés
# ---------------------------------------------------------------------------

@transaction.atomic
def deanery_create(*, name: str, diocese: Diocese, dean=None) -> Deanery:
    return Deanery.objects.create(name=name, diocese=diocese, dean=dean)


@transaction.atomic
def deanery_update(*, deanery: Deanery, name: str | None = None, dean=...) -> Deanery:
    if name is not None:
        deanery.name = name
    if dean is not ...:
        deanery.dean = dean
    deanery.save()
    return deanery


@transaction.atomic
def deanery_delete(*, deanery: Deanery) -> None:
    """Supprime un doyenné. ``Parish.deanery`` est SET_NULL : les paroisses
    rattachées sont simplement détachées (aucune donnée utilisateur en cascade),
    la suppression n'est donc pas bloquée par elles. Toute FK PROTECT résiduelle
    est convertie en erreur métier claire (même philosophie que ``parish_delete``).
    """
    from django.db.models import ProtectedError

    try:
        deanery.delete()
    except ProtectedError:
        raise ApplicationError(
            "Impossible de supprimer ce doyenné : des données le référencent."
        )

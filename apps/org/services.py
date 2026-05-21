from django.db import transaction

from apps.core.exceptions import ApplicationError
from apps.org.models import Diocese, Parish, Province, ReligiousCommunity, ReligiousOrder


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
def parish_create(*, name: str, diocese: Diocese, city: str = "", address: str = "") -> Parish:
    return Parish.objects.create(name=name, diocese=diocese, city=city, address=address)


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

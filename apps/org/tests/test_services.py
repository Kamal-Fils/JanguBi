import pytest

from apps.core.exceptions import ApplicationError
from apps.org.services import diocese_create, parish_create, province_create
from apps.org.tests.factories import DioceseFactory, ProvinceFactory


@pytest.mark.django_db
def test_province_create_success():
    province = province_create(name="Dakar", code="DAK")
    assert province.id is not None
    assert province.name == "Dakar"
    assert province.code == "DAK"
    assert province.country == "Senegal"


@pytest.mark.django_db
def test_province_create_duplicate_code_raises():
    province_create(name="Dakar", code="DAK")
    with pytest.raises(ApplicationError):
        province_create(name="Dakar Bis", code="DAK")


@pytest.mark.django_db
def test_diocese_create_success():
    province = ProvinceFactory()
    diocese = diocese_create(name="Diocèse de Dakar", code="DDK", province=province)
    assert diocese.id is not None
    assert diocese.province == province


@pytest.mark.django_db
def test_diocese_create_duplicate_code_raises():
    province = ProvinceFactory()
    diocese_create(name="Diocèse A", code="DA1", province=province)
    with pytest.raises(ApplicationError):
        diocese_create(name="Diocèse B", code="DA1", province=province)


@pytest.mark.django_db
def test_parish_create_success():
    diocese = DioceseFactory()
    parish = parish_create(name="Saint-Pierre", diocese=diocese, city="Dakar")
    assert parish.id is not None
    assert parish.diocese == diocese
    assert parish.city == "Dakar"

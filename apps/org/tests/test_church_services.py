import pytest

from apps.org.enums import ChurchType
from apps.org.models import Church
from apps.org.selectors import church_list, parish_main_church
from apps.org.services import church_create, parish_create

from .factories import DioceseFactory


@pytest.mark.django_db
def test_parish_create_auto_creates_main_church():
    # Arrange
    diocese = DioceseFactory()

    # Act
    parish = parish_create(name="Saint-Pierre", diocese=diocese, city="Dakar")

    # Assert
    main = parish_main_church(parish_id=parish.id)
    assert main is not None
    assert main.is_main is True
    assert main.church_type == ChurchType.PAROISSIALE
    assert main.name == "Saint-Pierre"


@pytest.mark.django_db
def test_church_create_second_main_demotes_first():
    # Arrange
    diocese = DioceseFactory()
    parish = parish_create(name="Saint-Pierre", diocese=diocese)
    first_main = parish_main_church(parish_id=parish.id)

    # Act
    new_main = church_create(parish=parish, name="Nouvelle principale", is_main=True)

    # Assert — la contrainte « une seule principale » est respectée
    first_main.refresh_from_db()
    assert first_main.is_main is False
    assert new_main.is_main is True
    assert Church.objects.filter(parish=parish, is_main=True).count() == 1


@pytest.mark.django_db
def test_church_create_secondary_keeps_main_intact():
    # Arrange
    diocese = DioceseFactory()
    parish = parish_create(name="Saint-Pierre", diocese=diocese)

    # Act
    succursale = church_create(
        parish=parish, name="Chapelle Sainte-Anne", church_type=ChurchType.CHAPELLE
    )

    # Assert
    assert succursale.is_main is False
    assert church_list(parish_id=parish.id).count() == 2
    assert Church.objects.filter(parish=parish, is_main=True).count() == 1

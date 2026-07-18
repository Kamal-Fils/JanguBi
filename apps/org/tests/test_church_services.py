import pytest

from apps.core.exceptions import ApplicationError
from apps.org.enums import ChurchType
from apps.org.models import Church
from apps.org.selectors import church_list, parish_main_church
from apps.org.services import church_create, church_delete, church_update, parish_create

from .factories import ChurchFactory, DioceseFactory, ParishFactory


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


@pytest.mark.django_db
def test_church_update_success_partial():
    # Arrange
    church = ChurchFactory(name="Ancien nom", city="Dakar")

    # Act
    updated = church_update(church=church, name="Nouveau nom")

    # Assert — mise à jour partielle : la ville n'est pas touchée
    church.refresh_from_db()
    assert updated.name == "Nouveau nom"
    assert church.name == "Nouveau nom"
    assert church.city == "Dakar"


@pytest.mark.django_db
def test_church_delete_success_secondary_without_data():
    # Arrange
    parish = ParishFactory()
    church = ChurchFactory(parish=parish)

    # Act
    church_delete(church=church)

    # Assert
    assert not Church.objects.filter(id=church.id).exists()


@pytest.mark.django_db
def test_church_delete_blocked_by_membership():
    # Arrange — Membership.church est CASCADE : jamais de cascade sur données utilisateur.
    from apps.users.models import Membership
    from apps.users.tests.factories import BaseUserFactory

    church = ChurchFactory()
    Membership.objects.create(user=BaseUserFactory(), church=church, is_primary=True)

    # Act & Assert
    with pytest.raises(ApplicationError) as exc:
        church_delete(church=church)
    assert "appartenances" in exc.value.message
    assert Church.objects.filter(id=church.id).exists()


@pytest.mark.django_db
def test_church_delete_main_blocked_when_others_exist():
    # Arrange — l'église principale n'est pas supprimable tant qu'il en existe d'autres.
    diocese = DioceseFactory()
    parish = parish_create(name="Saint-Pierre", diocese=diocese)
    main = parish_main_church(parish_id=parish.id)
    ChurchFactory(parish=parish)  # succursale

    # Act & Assert
    with pytest.raises(ApplicationError) as exc:
        church_delete(church=main)
    assert "église principale" in exc.value.message
    assert Church.objects.filter(id=main.id).exists()


@pytest.mark.django_db
def test_church_delete_main_allowed_when_only_church():
    # Arrange — dernière église de la paroisse : suppression autorisée (le
    # démantèlement complet passe sinon par parish_delete).
    diocese = DioceseFactory()
    parish = parish_create(name="Saint-Pierre", diocese=diocese)
    main = parish_main_church(parish_id=parish.id)

    # Act
    church_delete(church=main)

    # Assert
    assert not Church.objects.filter(parish=parish).exists()

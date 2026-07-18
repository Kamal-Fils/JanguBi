import pytest

from apps.core.exceptions import ApplicationError
from apps.org.services import (
    deanery_delete,
    deanery_update,
    diocese_create,
    diocese_delete,
    diocese_update,
    parish_create,
    province_create,
    province_delete,
    province_update,
)
from apps.org.tests.factories import (
    DeaneryFactory,
    DioceseFactory,
    ParishFactory,
    ProvinceFactory,
    ReligiousCommunityFactory,
)


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


# ---------------------------------------------------------------------------
# Provinces — update / delete
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_province_update_success():
    # Arrange
    province = ProvinceFactory(name="Ancien nom", code="ANC")

    # Act
    updated = province_update(province=province, name="Nouveau nom", code="NOU")

    # Assert
    province.refresh_from_db()
    assert updated.name == "Nouveau nom"
    assert province.name == "Nouveau nom"
    assert province.code == "NOU"


@pytest.mark.django_db
def test_province_update_duplicate_code_raises():
    # Arrange
    ProvinceFactory(code="DAK")
    province = ProvinceFactory(code="THI")

    # Act & Assert
    with pytest.raises(ApplicationError):
        province_update(province=province, code="DAK")


@pytest.mark.django_db
def test_province_delete_success_when_empty():
    # Arrange
    province = ProvinceFactory()

    # Act
    province_delete(province=province)

    # Assert
    from apps.org.models import Province

    assert not Province.objects.filter(id=province.id).exists()


@pytest.mark.django_db
def test_province_delete_blocked_by_diocese():
    # Arrange
    province = ProvinceFactory()
    DioceseFactory(province=province)

    # Act & Assert
    with pytest.raises(ApplicationError) as exc:
        province_delete(province=province)
    assert "diocèses rattachés" in exc.value.message
    from apps.org.models import Province

    assert Province.objects.filter(id=province.id).exists()


@pytest.mark.django_db
def test_province_delete_blocked_by_active_role_assignment():
    # Arrange — une affectation active (CASCADE) ne doit jamais partir en cascade.
    from apps.users.enums import UserRole
    from apps.users.models import RoleAssignment
    from apps.users.tests.factories import BaseUserFactory

    province = ProvinceFactory()
    RoleAssignment.objects.create(
        user=BaseUserFactory(),
        role=UserRole.PROVINCE_ADMIN,
        scope="province",
        province=province,
        is_active=True,
    )

    # Act & Assert
    with pytest.raises(ApplicationError) as exc:
        province_delete(province=province)
    assert "affectations actives" in exc.value.message


# ---------------------------------------------------------------------------
# Diocèses — update / delete
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_diocese_update_success():
    # Arrange
    diocese = DioceseFactory(name="Ancien nom", code="AND")

    # Act
    updated = diocese_update(diocese=diocese, name="Nouveau nom")

    # Assert — mise à jour partielle : le code n'est pas touché
    diocese.refresh_from_db()
    assert updated.name == "Nouveau nom"
    assert diocese.name == "Nouveau nom"
    assert diocese.code == "AND"


@pytest.mark.django_db
def test_diocese_delete_success_when_empty():
    # Arrange
    diocese = DioceseFactory()

    # Act
    diocese_delete(diocese=diocese)

    # Assert
    from apps.org.models import Diocese

    assert not Diocese.objects.filter(id=diocese.id).exists()


@pytest.mark.django_db
def test_diocese_delete_blocked_by_parish():
    # Arrange
    diocese = DioceseFactory()
    ParishFactory(diocese=diocese)

    # Act & Assert
    with pytest.raises(ApplicationError) as exc:
        diocese_delete(diocese=diocese)
    assert "paroisses rattachées" in exc.value.message


@pytest.mark.django_db
def test_diocese_delete_blocked_by_deanery():
    # Arrange
    diocese = DioceseFactory()
    DeaneryFactory(diocese=diocese)

    # Act & Assert
    with pytest.raises(ApplicationError) as exc:
        diocese_delete(diocese=diocese)
    assert "doyennés rattachés" in exc.value.message


@pytest.mark.django_db
def test_diocese_delete_blocked_by_religious_community():
    # Arrange
    diocese = DioceseFactory()
    ReligiousCommunityFactory(diocese=diocese)

    # Act & Assert
    with pytest.raises(ApplicationError) as exc:
        diocese_delete(diocese=diocese)
    assert "communautés religieuses" in exc.value.message


# ---------------------------------------------------------------------------
# Doyennés — update / delete
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_deanery_update_success():
    # Arrange
    from apps.users.tests.factories import BaseUserFactory

    deanery = DeaneryFactory(name="Ancien nom")
    dean = BaseUserFactory()

    # Act
    updated = deanery_update(deanery=deanery, name="Nouveau nom", dean=dean)

    # Assert
    deanery.refresh_from_db()
    assert updated.name == "Nouveau nom"
    assert deanery.dean == dean


@pytest.mark.django_db
def test_deanery_update_partial_keeps_dean():
    # Arrange — le sentinel `...` distingue « non fourni » de « null »
    from apps.users.tests.factories import BaseUserFactory

    dean = BaseUserFactory()
    deanery = DeaneryFactory(dean=dean)

    # Act
    deanery_update(deanery=deanery, name="Autre nom")

    # Assert
    deanery.refresh_from_db()
    assert deanery.dean == dean


@pytest.mark.django_db
def test_deanery_delete_success_when_empty():
    # Arrange
    deanery = DeaneryFactory()

    # Act
    deanery_delete(deanery=deanery)

    # Assert
    from apps.org.models import Deanery

    assert not Deanery.objects.filter(id=deanery.id).exists()


@pytest.mark.django_db
def test_deanery_delete_detaches_parishes():
    # Arrange — Parish.deanery est SET_NULL : suppression autorisée, paroisses détachées.
    deanery = DeaneryFactory()
    parish = ParishFactory(deanery=deanery)

    # Act
    deanery_delete(deanery=deanery)

    # Assert
    from apps.org.models import Deanery

    parish.refresh_from_db()
    assert parish.deanery is None
    assert not Deanery.objects.filter(id=deanery.id).exists()

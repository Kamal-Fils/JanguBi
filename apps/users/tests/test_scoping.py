import pytest

from apps.org.tests.factories import DioceseFactory, ParishFactory
from apps.users.enums import RoleScope, UserRole
from apps.users.scoping import (
    accessible_parish_ids,
    parish_principal_cure,
    superior_of,
    user_can_admin_parish,
)
from apps.users.services_roles import role_assignment_create

from .factories import BaseUserFactory, ProfileFactory


@pytest.mark.django_db
def test_diocese_admin_can_admin_parish_in_own_diocese_only():
    # Arrange
    diocese = DioceseFactory()
    parish = ParishFactory(diocese=diocese)
    other_parish = ParishFactory()  # autre diocèse
    admin = BaseUserFactory(role=UserRole.DIOCESE_ADMIN)
    role_assignment_create(
        user=admin, role=UserRole.DIOCESE_ADMIN, scope=RoleScope.DIOCESE, diocese=diocese
    )

    # Act & Assert
    assert user_can_admin_parish(admin, parish.id) is True
    assert user_can_admin_parish(admin, other_parish.id) is False


@pytest.mark.django_db
def test_accessible_parish_ids_expands_diocese_admin_to_all_parishes():
    # Arrange
    diocese = DioceseFactory()
    p1 = ParishFactory(diocese=diocese)
    p2 = ParishFactory(diocese=diocese)
    ParishFactory()  # autre diocèse, ne doit pas apparaître
    admin = BaseUserFactory(role=UserRole.DIOCESE_ADMIN)
    role_assignment_create(
        user=admin, role=UserRole.DIOCESE_ADMIN, scope=RoleScope.DIOCESE, diocese=diocese
    )

    # Act
    ids = accessible_parish_ids(admin)

    # Assert
    assert ids == {p1.id, p2.id}


@pytest.mark.django_db
def test_principal_cure_and_superior_of_fidele():
    # Arrange
    parish = ParishFactory()
    cure = BaseUserFactory(role=UserRole.PARISH_ADMIN)
    role_assignment_create(
        user=cure, role=UserRole.PARISH_ADMIN, scope=RoleScope.PARISH,
        parish=parish, is_principal=True,
    )
    fidele = BaseUserFactory(role=UserRole.FIDELE)
    ProfileFactory(user=fidele, primary_parish=parish)

    # Act & Assert
    assert parish_principal_cure(parish.id) == cure
    assert superior_of(fidele) == cure


@pytest.mark.django_db
def test_second_principal_demotes_first():
    # Arrange
    parish = ParishFactory()
    cure1 = BaseUserFactory(role=UserRole.PARISH_ADMIN)
    cure2 = BaseUserFactory(role=UserRole.PARISH_ADMIN)
    role_assignment_create(
        user=cure1, role=UserRole.PARISH_ADMIN, scope=RoleScope.PARISH,
        parish=parish, is_principal=True,
    )

    # Act — un 2ᵉ curé principal démote le 1ᵉ (contrainte d'unicité)
    role_assignment_create(
        user=cure2, role=UserRole.PARISH_ADMIN, scope=RoleScope.PARISH,
        parish=parish, is_principal=True,
    )

    # Assert
    assert parish_principal_cure(parish.id) == cure2

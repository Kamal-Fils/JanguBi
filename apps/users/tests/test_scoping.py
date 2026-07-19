import pytest

from apps.org.tests.factories import (
    ChurchFactory,
    DioceseFactory,
    ParishFactory,
    ProvinceFactory,
)
from apps.users.enums import PastoralRole, RoleScope, UserRole
from apps.users.scoping import (
    accessible_parish_ids,
    parish_principal_cure,
    superior_of,
    user_can_admin_parish,
    user_has_pastoral_authority,
)
from apps.users.services_memberships import membership_create
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


# ---------------------------------------------------------------------------
# Autorité PASTORALE (dimension orthogonale à RoleAssignment)
# ---------------------------------------------------------------------------
# Helper promu ici depuis apps/agenda/services.py : agenda et spiritual le
# partagent désormais, avec des `allowed_roles` propres à chaque acte (matrice
# §16). Les tests ci-dessous asservissent le contrat COMMUN.

def _clergy_attached_to(church, pastoral_role):
    """Clergé « nu » : rôle PASTORAL + appartenance réelle, AUCUNE RoleAssignment."""
    user = BaseUserFactory(pastoral_role=pastoral_role)
    membership_create(user=user, church=church, is_primary=True)
    user.refresh_from_db()  # diocese/province remplis par signal via .update()
    return user


@pytest.mark.django_db
def test_pastoral_authority_covers_the_parish_of_ones_own_membership():
    # Arrange
    church = ChurchFactory()
    priest = _clergy_attached_to(church, PastoralRole.PRETRE)

    # Act & Assert — aucune RoleAssignment, et pourtant l'autorité est là.
    assert user_can_admin_parish(priest, church.parish_id) is False
    assert user_has_pastoral_authority(
        user=priest, scope_type="parish", scope_parish_id=church.parish_id
    ) is True


@pytest.mark.django_db
def test_pastoral_authority_is_fail_closed_on_a_foreign_parish():
    # Arrange
    church = ChurchFactory()
    priest = _clergy_attached_to(church, PastoralRole.PRETRE)

    # Act & Assert — un id arbitraire venu du client n'ouvre aucun droit.
    assert user_has_pastoral_authority(
        user=priest, scope_type="parish", scope_parish_id=ParishFactory().id
    ) is False


@pytest.mark.django_db
def test_pastoral_authority_never_grants_the_global_scope():
    # Arrange
    church = ChurchFactory()

    # Act & Assert — la portée globale reste administrative (province/national).
    for role in (PastoralRole.PRETRE, PastoralRole.EVEQUE, PastoralRole.ARCHEVEQUE):
        clergy = _clergy_attached_to(ChurchFactory(parish=church.parish), role)
        assert user_has_pastoral_authority(user=clergy, scope_type="global") is False


@pytest.mark.django_db
def test_pastoral_authority_refuses_a_religious_even_when_explicitly_allowed():
    """Plafond dur : ``allowed_roles`` est TOUJOURS intersecté avec
    ``PASTORAL_TERRITORIAL_ROLES``. Un appelant ne peut pas ouvrir la voie
    pastorale au religieux ni au fidèle, même en le demandant."""
    # Arrange
    church = ChurchFactory()
    religious = _clergy_attached_to(church, PastoralRole.RELIGIEUX)

    # Act & Assert
    assert user_has_pastoral_authority(
        user=religious,
        scope_type="parish",
        scope_parish_id=church.parish_id,
        allowed_roles=frozenset({PastoralRole.RELIGIEUX, PastoralRole.PRETRE}),
    ) is False


@pytest.mark.django_db
def test_pastoral_authority_narrows_to_the_roles_the_act_concerns():
    # Le même diacre porte l'autorité pour l'agenda (il organise) et pas pour la
    # réflexion pastorale (il ne publie pas) — c'est `allowed_roles` qui tranche.
    # Arrange
    church = ChurchFactory()
    deacon = _clergy_attached_to(church, PastoralRole.DIACRE)
    organizer_roles = frozenset({PastoralRole.DIACRE, PastoralRole.PRETRE})
    publisher_roles = frozenset({PastoralRole.PRETRE})

    # Act & Assert
    assert user_has_pastoral_authority(
        user=deacon, scope_type="parish", scope_parish_id=church.parish_id,
        allowed_roles=organizer_roles,
    ) is True
    assert user_has_pastoral_authority(
        user=deacon, scope_type="parish", scope_parish_id=church.parish_id,
        allowed_roles=publisher_roles,
    ) is False


@pytest.mark.django_db
def test_archbishop_pastoral_authority_spans_every_diocese_of_his_province():
    # Arrange
    province = ProvinceFactory()
    home = DioceseFactory(province=province)
    sister = DioceseFactory(province=province)
    outside = DioceseFactory()  # autre province
    church = ChurchFactory(parish=ParishFactory(diocese=home))
    archbishop = _clergy_attached_to(church, PastoralRole.ARCHEVEQUE)

    # Act & Assert
    assert user_has_pastoral_authority(
        user=archbishop, scope_type="diocese", scope_diocese_id=sister.id
    ) is True
    assert user_has_pastoral_authority(
        user=archbishop, scope_type="diocese", scope_diocese_id=outside.id
    ) is False

import pytest
from django.utils import timezone

from apps.clergy_accounts.models import ClergicalInvitation
from apps.clergy_accounts.services import invitation_create, invitation_accept, invitation_revoke
from apps.core.exceptions import ApplicationError
from apps.org.tests.factories import DioceseFactory, ParishFactory
from apps.users.enums import PastoralRole, RoleScope, UserRole
from apps.users.models import RoleAssignment
from apps.users.tests.factories import BaseUserFactory, SuperAdminFactory

from .factories import ClergicalInvitationFactory


@pytest.fixture
def diocese():
    return DioceseFactory()


@pytest.fixture
def eveque(diocese):
    # Évêque = pastoral_role EVEQUE + RoleAssignment(diocese_admin) sur SON diocèse
    # (source de vérité d'autorité). user.role reste 'fidele'.
    user = BaseUserFactory(role=UserRole.FIDELE)
    user.pastoral_role = PastoralRole.EVEQUE
    user.diocese_id = diocese.id
    user.save(update_fields=["pastoral_role", "diocese_id"])
    RoleAssignment.objects.create(
        user=user,
        role=UserRole.DIOCESE_ADMIN,
        scope=RoleScope.DIOCESE,
        diocese=diocese,
        is_active=True,
    )
    return user


@pytest.fixture
def pretre():
    user = BaseUserFactory(role=UserRole.FIDELE)
    user.pastoral_role = PastoralRole.PRETRE
    user.save(update_fields=["pastoral_role"])
    return user


@pytest.fixture
def super_admin():
    return SuperAdminFactory()


@pytest.mark.django_db
def test_invitation_create_by_eveque_for_pretre(eveque):
    # Arrange & Act
    invitation = invitation_create(
        inviter=eveque,
        email="pretre@example.com",
        first_name="Abbé",
        last_name="Sène",
        pastoral_role=PastoralRole.PRETRE,
    )

    # Assert
    assert invitation.id is not None
    assert invitation.email == "pretre@example.com"
    assert invitation.pastoral_role == PastoralRole.PRETRE
    assert invitation.status == ClergicalInvitation.Status.PENDING
    assert invitation.expires_at > timezone.now()


@pytest.mark.django_db
def test_invitation_create_by_super_admin_for_archeveque(super_admin):
    invitation = invitation_create(
        inviter=super_admin,
        email="archeveque@example.com",
        first_name="Mgr",
        last_name="Diallo",
        pastoral_role=PastoralRole.ARCHEVEQUE,
    )
    assert invitation.pastoral_role == PastoralRole.ARCHEVEQUE


@pytest.mark.django_db
def test_invitation_create_eveque_cannot_invite_archeveque(eveque):
    with pytest.raises(ApplicationError):
        invitation_create(
            inviter=eveque,
            email="archeveque@example.com",
            first_name="Mgr",
            last_name="X",
            pastoral_role=PastoralRole.ARCHEVEQUE,
        )


@pytest.mark.django_db
def test_invitation_create_fidele_cannot_invite(pretre):
    fidele = BaseUserFactory(role=UserRole.FIDELE)
    with pytest.raises(ApplicationError):
        invitation_create(
            inviter=fidele,
            email="x@example.com",
            first_name="X",
            last_name="Y",
            pastoral_role=PastoralRole.PRETRE,
        )


@pytest.mark.django_db
def test_invitation_create_duplicate_pending_raises(eveque):
    invitation_create(
        inviter=eveque,
        email="dup@example.com",
        first_name="A",
        last_name="B",
        pastoral_role=PastoralRole.DIACRE,
    )
    with pytest.raises(ApplicationError):
        invitation_create(
            inviter=eveque,
            email="dup@example.com",
            first_name="A",
            last_name="B",
            pastoral_role=PastoralRole.DIACRE,
        )


@pytest.mark.django_db
def test_invitation_accept_success(eveque):
    user = BaseUserFactory(email="new_pretre@example.com")
    invitation = ClergicalInvitationFactory(email=user.email, created_by=eveque)

    result = invitation_accept(token=str(invitation.token), user=user)

    assert result.status == ClergicalInvitation.Status.ACCEPTED
    assert result.accepted_by == user

    user.refresh_from_db()
    assert user.pastoral_role == invitation.pastoral_role


@pytest.mark.django_db
def test_invitation_accept_wrong_email_raises(eveque):
    invitation = ClergicalInvitationFactory(email="other@example.com", created_by=eveque)
    wrong_user = BaseUserFactory(email="wrong@example.com")

    with pytest.raises(ApplicationError):
        invitation_accept(token=str(invitation.token), user=wrong_user)


@pytest.mark.django_db
def test_invitation_accept_expired_raises(eveque):
    invitation = ClergicalInvitationFactory(
        created_by=eveque,
        expires_at=timezone.now() - timezone.timedelta(hours=1),
    )
    user = BaseUserFactory(email=invitation.email)

    with pytest.raises(ApplicationError):
        invitation_accept(token=str(invitation.token), user=user)


@pytest.mark.django_db
def test_invitation_revoke_success(eveque):
    invitation = ClergicalInvitationFactory(created_by=eveque)
    result = invitation_revoke(invitation=invitation, revoker=eveque)
    assert result.status == ClergicalInvitation.Status.REVOKED


@pytest.mark.django_db
def test_invitation_revoke_already_accepted_raises(eveque):
    invitation = ClergicalInvitationFactory(
        created_by=eveque,
        status=ClergicalInvitation.Status.ACCEPTED,
    )
    with pytest.raises(ApplicationError):
        invitation_revoke(invitation=invitation, revoker=eveque)


# --- Lot 1 / Phase 4 : invitation → RoleAssignment scopée --------------------


@pytest.mark.django_db
def test_invitation_create_accepts_parish_target(eveque, diocese):
    # Arrange & Act — paroisse cible DANS le diocèse de l'évêque (autorité OK).
    parish = ParishFactory(diocese=diocese)
    invitation = invitation_create(
        inviter=eveque,
        email="cure@example.com",
        first_name="Abbé",
        last_name="Diouf",
        pastoral_role=PastoralRole.PRETRE,
        parish_id=parish.id,
    )

    # Assert
    assert invitation.parish_id == parish.id


@pytest.mark.django_db
def test_invitation_create_cross_diocese_parish_forbidden(eveque):
    # EXPLOIT 🔴-1 : un évêque du diocèse X invite dans une paroisse du diocèse Y.
    # Avant le fix : RoleAssignment(parish_admin) plantée hors territoire.
    foreign_parish = ParishFactory()  # autre diocèse (≠ celui de l'évêque)

    with pytest.raises(ApplicationError, match="autorité"):
        invitation_create(
            inviter=eveque,
            email="intrus@example.com",
            first_name="Abbé",
            last_name="Intrus",
            pastoral_role=PastoralRole.PRETRE,
            parish_id=foreign_parish.id,
        )


@pytest.mark.django_db
def test_invitation_create_unknown_parish_raises(eveque):
    with pytest.raises(ApplicationError):
        invitation_create(
            inviter=eveque,
            email="cure@example.com",
            first_name="Abbé",
            last_name="Diouf",
            pastoral_role=PastoralRole.PRETRE,
            parish_id=999999,
        )


@pytest.mark.django_db
def test_invitation_accept_pretre_creates_principal_role_assignment(eveque, diocese):
    # Arrange — invitation de curé ciblant une paroisse du diocèse de l'évêque
    parish = ParishFactory(diocese=diocese)
    user = BaseUserFactory(
        email="cure2@example.com", is_active=False, is_verified=False
    )
    invitation = ClergicalInvitationFactory(
        email=user.email,
        created_by=eveque,
        pastoral_role=PastoralRole.PRETRE,
        parish=parish,
        diocese=parish.diocese,
    )

    # Act
    invitation_accept(token=str(invitation.token), user=user)

    # Assert — compte vérifié/actif + capacité scopée créée
    user.refresh_from_db()
    assert user.is_verified is True
    assert user.is_active is True
    assert user.pastoral_role == PastoralRole.PRETRE
    # 🟠 province dérivée du diocèse (plus de province NULL)
    assert user.diocese_id == parish.diocese_id
    assert user.province_id == parish.diocese.province_id

    ra = RoleAssignment.objects.get(user=user, is_active=True)
    assert ra.role == UserRole.PARISH_ADMIN
    assert ra.scope == RoleScope.PARISH
    assert ra.parish_id == parish.id
    assert ra.is_principal is True
    assert ra.granted_by_id == eveque.id


@pytest.mark.django_db
def test_invitation_accept_without_target_sets_account_but_no_role_assignment(eveque):
    # Invitation sans cible (legacy) : compte activé, mais pas de RoleAssignment.
    user = BaseUserFactory(email="abbe@example.com", is_active=False, is_verified=False)
    invitation = ClergicalInvitationFactory(
        email=user.email, created_by=eveque, pastoral_role=PastoralRole.PRETRE
    )

    invitation_accept(token=str(invitation.token), user=user)

    user.refresh_from_db()
    assert user.is_verified is True
    assert user.is_active is True
    assert not RoleAssignment.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_eveque_cannot_invite_eveque(eveque):
    with pytest.raises(ApplicationError):
        invitation_create(
            inviter=eveque,
            email="autre_eveque@example.com",
            first_name="Mgr",
            last_name="Ndiaye",
            pastoral_role=PastoralRole.EVEQUE,
        )


@pytest.mark.django_db
def test_super_admin_can_invite_eveque(super_admin):
    diocese = DioceseFactory()
    invitation = invitation_create(
        inviter=super_admin,
        email="eveque@example.com",
        first_name="Mgr",
        last_name="Faye",
        pastoral_role=PastoralRole.EVEQUE,
        diocese_id=diocese.id,
    )
    assert invitation.pastoral_role == PastoralRole.EVEQUE

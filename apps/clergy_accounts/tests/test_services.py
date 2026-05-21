import pytest
from django.utils import timezone

from apps.clergy_accounts.models import ClergicalInvitation
from apps.clergy_accounts.services import invitation_create, invitation_accept, invitation_revoke
from apps.core.exceptions import ApplicationError
from apps.users.enums import PastoralRole, UserRole
from apps.users.tests.factories import BaseUserFactory, SuperAdminFactory

from .factories import ClergicalInvitationFactory


@pytest.fixture
def eveque():
    user = BaseUserFactory(role=UserRole.FIDELE)
    user.pastoral_role = PastoralRole.EVEQUE
    user.save(update_fields=["pastoral_role"])
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

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.clergy_accounts.models import ClergicalInvitation
from apps.users.enums import PastoralRole, UserRole
from apps.users.tests.factories import BaseUserFactory, SuperAdminFactory

from .factories import ClergicalInvitationFactory


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def eveque_client():
    client = APIClient()
    user = BaseUserFactory(role=UserRole.FIDELE)
    user.pastoral_role = PastoralRole.EVEQUE
    user.save(update_fields=["pastoral_role"])
    client.force_authenticate(user=user)
    client._user = user
    return client


@pytest.fixture
def super_admin_client():
    client = APIClient()
    user = SuperAdminFactory()
    client.force_authenticate(user=user)
    client._user = user
    return client


@pytest.fixture
def fidele_client():
    client = APIClient()
    user = BaseUserFactory()
    client.force_authenticate(user=user)
    client._user = user
    return client


@pytest.mark.django_db
def test_create_invitation_returns_201(eveque_client):
    url = reverse("api:clergy-accounts:invitations-list-create")
    response = eveque_client.post(
        url,
        {
            "email": "pretre@example.com",
            "first_name": "Abbé",
            "last_name": "Sène",
            "pastoral_role": "pretre",
        },
        format="json",
    )
    assert response.status_code == 201
    assert response.data["email"] == "pretre@example.com"
    assert response.data["pastoral_role"] == "pretre"


@pytest.mark.django_db
def test_create_invitation_fidele_forbidden(fidele_client):
    url = reverse("api:clergy-accounts:invitations-list-create")
    response = fidele_client.post(
        url,
        {"email": "x@example.com", "first_name": "X", "last_name": "Y", "pastoral_role": "pretre"},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_create_invitation_requires_auth(api_client):
    url = reverse("api:clergy-accounts:invitations-list-create")
    response = api_client.post(url, {}, format="json")
    assert response.status_code == 401


@pytest.mark.django_db
def test_list_invitations_returns_200(eveque_client):
    ClergicalInvitationFactory(created_by=eveque_client._user)
    url = reverse("api:clergy-accounts:invitations-list-create")
    response = eveque_client.get(url)
    assert response.status_code == 200
    assert response.data["count"] >= 1


@pytest.mark.django_db
def test_validate_token_returns_200(eveque_client):
    invitation = ClergicalInvitationFactory(created_by=eveque_client._user)
    url = reverse("api:clergy-accounts:invitations-validate")
    response = eveque_client.get(url, {"token": str(invitation.token)})
    assert response.status_code == 200
    assert response.data["email"] == invitation.email


@pytest.mark.django_db
def test_validate_token_missing_returns_400(api_client):
    url = reverse("api:clergy-accounts:invitations-validate")
    response = api_client.get(url)
    assert response.status_code == 400


@pytest.mark.django_db
def test_revoke_invitation_returns_200(eveque_client):
    invitation = ClergicalInvitationFactory(created_by=eveque_client._user)
    url = reverse("api:clergy-accounts:invitations-revoke", kwargs={"invitation_id": invitation.id})
    response = eveque_client.post(url)
    assert response.status_code == 200
    assert response.data["status"] == "revoked"


@pytest.mark.django_db
def test_accept_invitation_returns_200(eveque_client):
    user = BaseUserFactory(email="new@example.com")
    invitation = ClergicalInvitationFactory(email="new@example.com", created_by=eveque_client._user)

    client = APIClient()
    client.force_authenticate(user=user)

    url = reverse("api:clergy-accounts:invitations-accept")
    response = client.post(url, {"token": str(invitation.token)}, format="json")
    assert response.status_code == 200
    assert response.data["status"] == "accepted"

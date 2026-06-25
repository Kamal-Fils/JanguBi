import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.org.tests.factories import ChurchFactory, ParishFactory
from apps.transfers.models import ParishTransferRequest, TransferStatus
from apps.users.enums import RoleScope, UserOnboardingState, UserRole
from apps.users.models import BaseUser, Membership
from apps.users.services_memberships import membership_create
from apps.users.services_roles import role_assignment_create


def _make_user(email, onboarding=UserOnboardingState.COMPLETED):
    user = BaseUser.objects.create_user(
        email=email,
        password="StrongPassw0rd!",
        role="fidele",
        phone_number=f"+221770{abs(hash(email)) % 1_000_000:06d}",
        is_active=True,
        is_verified=True,
    )
    user.onboarding_state = onboarding
    user.save(update_fields=["onboarding_state"])
    return user


def _parish_admin_for(email, parish):
    """Admin paroissial scopé sur ``parish`` (RoleAssignment, source de vérité)."""
    admin = _make_user(email)
    role_assignment_create(
        user=admin,
        role=UserRole.PARISH_ADMIN,
        scope=RoleScope.PARISH,
        parish=parish,
    )
    return admin


@pytest.fixture
def fidele_client(db):
    client = APIClient()
    user = _make_user("fidele_tr@test.com")
    membership_create(user=user, church=ChurchFactory(), is_primary=True)
    client.force_authenticate(user=user)
    client._user = user
    return client


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_create_transfer_201(fidele_client):
    destination = ParishFactory()
    url = reverse("api:transfers:create")
    resp = fidele_client.post(
        url,
        {"destination_parish_id": destination.pk, "reason": "Déménagement"},
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED
    assert resp.data["status"] == TransferStatus.PENDING
    assert resp.data["destination_parish_name"] == destination.name
    assert ParishTransferRequest.objects.filter(requester=fidele_client._user).count() == 1


@pytest.mark.django_db
def test_create_transfer_requires_auth():
    client = APIClient()
    url = reverse("api:transfers:create")
    resp = client.post(url, {"destination_parish_id": 1}, format="json")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_create_transfer_unknown_destination_400(fidele_client):
    url = reverse("api:transfers:create")
    resp = fidele_client.post(url, {"destination_parish_id": 999999}, format="json")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_create_transfer_blocked_when_onboarding_pending():
    user = _make_user("pending_tr@test.com", UserOnboardingState.PENDING_PARISH_SELECTION)
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse("api:transfers:create")
    resp = client.post(
        url, {"destination_parish_id": ParishFactory().pk}, format="json"
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# My request
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_my_request_returns_404_when_none(fidele_client):
    url = reverse("api:transfers:my-request")
    resp = fidele_client.get(url)
    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_my_request_returns_latest(fidele_client):
    destination = ParishFactory()
    create_url = reverse("api:transfers:create")
    fidele_client.post(
        create_url, {"destination_parish_id": destination.pk}, format="json"
    )
    url = reverse("api:transfers:my-request")
    resp = fidele_client.get(url)
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["destination_parish_name"] == destination.name


@pytest.mark.django_db
def test_my_request_requires_auth():
    client = APIClient()
    url = reverse("api:transfers:my-request")
    resp = client.get(url)
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------------------
# Admin list
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_admin_list_forbidden_for_fidele(fidele_client):
    url = reverse("api:transfers:admin-list")
    resp = fidele_client.get(url)
    assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_admin_list_scoped_to_managed_parishes():
    # Arrange — un transfert vers la paroisse administrée, un autre hors périmètre.
    requester = _make_user("req_list@test.com")
    membership_create(user=requester, church=ChurchFactory(), is_primary=True)
    managed = ParishFactory()
    ParishTransferRequest.objects.create(
        requester=requester, origin_parish=ParishFactory(), destination_parish=managed
    )
    other = _make_user("req_other@test.com")
    membership_create(user=other, church=ChurchFactory(), is_primary=True)
    ParishTransferRequest.objects.create(
        requester=other, origin_parish=ParishFactory(), destination_parish=ParishFactory()
    )
    admin = _parish_admin_for("admin_list@test.com", managed)
    client = APIClient()
    client.force_authenticate(user=admin)

    # Act
    resp = client.get(reverse("api:transfers:admin-list"))

    # Assert — pagination {count, results}, scopé à la paroisse gérée.
    assert resp.status_code == status.HTTP_200_OK
    assert "results" in resp.data
    assert resp.data["count"] == 1


# ---------------------------------------------------------------------------
# Approve / reject / acknowledge
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_approve_by_origin_admin():
    requester = _make_user("req_approve@test.com")
    origin = ParishFactory()
    transfer = ParishTransferRequest.objects.create(
        requester=requester, origin_parish=origin, destination_parish=ParishFactory()
    )
    admin = _parish_admin_for("origin_admin@test.com", origin)
    client = APIClient()
    client.force_authenticate(user=admin)

    url = reverse("api:transfers:approve", kwargs={"transfer_id": transfer.pk})
    resp = client.post(url)

    assert resp.status_code == status.HTTP_200_OK
    transfer.refresh_from_db()
    assert transfer.status == TransferStatus.APPROVED_BY_ORIGIN


@pytest.mark.django_db
def test_approve_forbidden_for_unrelated_admin():
    requester = _make_user("req_approve2@test.com")
    transfer = ParishTransferRequest.objects.create(
        requester=requester, origin_parish=ParishFactory(), destination_parish=ParishFactory()
    )
    admin = _parish_admin_for("unrelated_admin@test.com", ParishFactory())
    client = APIClient()
    client.force_authenticate(user=admin)

    url = reverse("api:transfers:approve", kwargs={"transfer_id": transfer.pk})
    resp = client.post(url)
    assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_reject_by_origin_admin():
    requester = _make_user("req_reject@test.com")
    origin = ParishFactory()
    transfer = ParishTransferRequest.objects.create(
        requester=requester, origin_parish=origin, destination_parish=ParishFactory()
    )
    admin = _parish_admin_for("origin_admin_rej@test.com", origin)
    client = APIClient()
    client.force_authenticate(user=admin)

    url = reverse("api:transfers:reject", kwargs={"transfer_id": transfer.pk})
    resp = client.post(url, {"reason": "Dossier incomplet"}, format="json")

    assert resp.status_code == status.HTTP_200_OK
    transfer.refresh_from_db()
    assert transfer.status == TransferStatus.REJECTED
    assert transfer.rejection_reason == "Dossier incomplet"


@pytest.mark.django_db
def test_acknowledge_by_destination_admin_completes_and_moves_user():
    # Arrange — demandeur rattaché à une origine, destination dotée d'une église.
    requester = _make_user("req_ack@test.com")
    membership_create(user=requester, church=ChurchFactory(), is_primary=True)
    destination_church = ChurchFactory(is_main=True)
    destination = destination_church.parish
    transfer = ParishTransferRequest.objects.create(
        requester=requester,
        origin_parish=ParishFactory(),
        destination_parish=destination,
        status=TransferStatus.APPROVED_BY_ORIGIN,
    )
    admin = _parish_admin_for("dest_admin@test.com", destination)
    client = APIClient()
    client.force_authenticate(user=admin)

    # Act
    url = reverse("api:transfers:acknowledge", kwargs={"transfer_id": transfer.pk})
    resp = client.post(url)

    # Assert
    assert resp.status_code == status.HTTP_200_OK
    transfer.refresh_from_db()
    assert transfer.status == TransferStatus.COMPLETED
    primary = Membership.objects.get(user=requester, is_primary=True)
    assert primary.church_id == destination_church.pk


@pytest.mark.django_db
def test_acknowledge_forbidden_for_origin_admin():
    requester = _make_user("req_ack2@test.com")
    membership_create(user=requester, church=ChurchFactory(), is_primary=True)
    origin = ParishFactory()
    transfer = ParishTransferRequest.objects.create(
        requester=requester,
        origin_parish=origin,
        destination_parish=ChurchFactory(is_main=True).parish,
        status=TransferStatus.APPROVED_BY_ORIGIN,
    )
    # admin de l'ORIGINE — pas de la destination → 403 sur acknowledge
    admin = _parish_admin_for("origin_only_admin@test.com", origin)
    client = APIClient()
    client.force_authenticate(user=admin)

    url = reverse("api:transfers:acknowledge", kwargs={"transfer_id": transfer.pk})
    resp = client.post(url)
    assert resp.status_code == status.HTTP_403_FORBIDDEN

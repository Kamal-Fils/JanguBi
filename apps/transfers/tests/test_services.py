import pytest

from apps.core.exceptions import ApplicationError
from apps.org.tests.factories import ChurchFactory, ParishFactory
from apps.transfers.models import ParishTransferRequest, TransferStatus
from apps.transfers.services import (
    transfer_acknowledge,
    transfer_approve,
    transfer_create,
    transfer_reject,
)
from apps.users.enums import UserOnboardingState
from apps.users.models import BaseUser, Membership
from apps.users.services_memberships import membership_create


def _make_user(email):
    user = BaseUser.objects.create_user(
        email=email,
        password="StrongPassw0rd!",
        role="fidele",
        phone_number=f"+221770{abs(hash(email)) % 1_000_000:06d}",
        is_active=True,
        is_verified=True,
    )
    user.onboarding_state = UserOnboardingState.COMPLETED
    user.save(update_fields=["onboarding_state"])
    return user


@pytest.mark.django_db
def test_transfer_create_success_derives_origin_from_primary_membership():
    # Arrange — le demandeur a une appartenance principale (paroisse d'origine).
    requester = _make_user("creator@test.com")
    origin_church = ChurchFactory()
    membership_create(user=requester, church=origin_church, is_primary=True)
    destination = ParishFactory()

    # Act
    transfer = transfer_create(
        requester=requester, destination_parish=destination, reason="Déménagement"
    )

    # Assert
    assert transfer.id is not None
    assert transfer.status == TransferStatus.PENDING
    assert transfer.origin_parish_id == origin_church.parish_id
    assert transfer.destination_parish_id == destination.pk
    assert transfer.reason == "Déménagement"


@pytest.mark.django_db
def test_transfer_create_requires_destination():
    requester = _make_user("nodest@test.com")
    with pytest.raises(ApplicationError):
        transfer_create(requester=requester, destination_parish=None)


@pytest.mark.django_db
def test_transfer_create_rejects_same_origin_and_destination():
    # Arrange — destination == paroisse principale du demandeur.
    requester = _make_user("same@test.com")
    church = ChurchFactory()
    membership_create(user=requester, church=church, is_primary=True)

    # Act & Assert
    with pytest.raises(ApplicationError):
        transfer_create(requester=requester, destination_parish=church.parish)


@pytest.mark.django_db
def test_transfer_create_blocks_second_active_request():
    # Arrange — une demande active existe déjà.
    requester = _make_user("dup@test.com")
    membership_create(user=requester, church=ChurchFactory(), is_primary=True)
    transfer_create(requester=requester, destination_parish=ParishFactory())

    # Act & Assert
    with pytest.raises(ApplicationError):
        transfer_create(requester=requester, destination_parish=ParishFactory())


@pytest.mark.django_db
def test_transfer_create_allowed_after_terminal_request():
    # Arrange — une demande rejetée (terminale) ne bloque pas une nouvelle demande.
    requester = _make_user("again@test.com")
    membership_create(user=requester, church=ChurchFactory(), is_primary=True)
    first = transfer_create(requester=requester, destination_parish=ParishFactory())
    transfer_reject(transfer=first, reason="Refusé")

    # Act
    second = transfer_create(requester=requester, destination_parish=ParishFactory())

    # Assert
    assert second.id != first.id
    assert ParishTransferRequest.objects.filter(requester=requester).count() == 2


@pytest.mark.django_db
def test_transfer_approve_moves_pending_to_approved():
    requester = _make_user("approve@test.com")
    membership_create(user=requester, church=ChurchFactory(), is_primary=True)
    transfer = transfer_create(requester=requester, destination_parish=ParishFactory())

    transfer = transfer_approve(transfer=transfer)

    assert transfer.status == TransferStatus.APPROVED_BY_ORIGIN


@pytest.mark.django_db
def test_transfer_approve_rejects_non_pending():
    requester = _make_user("approve2@test.com")
    membership_create(user=requester, church=ChurchFactory(), is_primary=True)
    transfer = transfer_create(requester=requester, destination_parish=ParishFactory())
    transfer_approve(transfer=transfer)

    with pytest.raises(ApplicationError):
        transfer_approve(transfer=transfer)


@pytest.mark.django_db
def test_transfer_reject_requires_reason():
    requester = _make_user("noreason@test.com")
    membership_create(user=requester, church=ChurchFactory(), is_primary=True)
    transfer = transfer_create(requester=requester, destination_parish=ParishFactory())

    with pytest.raises(ApplicationError):
        transfer_reject(transfer=transfer, reason="")


@pytest.mark.django_db
def test_transfer_reject_sets_status_and_reason():
    requester = _make_user("reject@test.com")
    membership_create(user=requester, church=ChurchFactory(), is_primary=True)
    transfer = transfer_create(requester=requester, destination_parish=ParishFactory())

    transfer = transfer_reject(transfer=transfer, reason="Dossier incomplet")

    assert transfer.status == TransferStatus.REJECTED
    assert transfer.rejection_reason == "Dossier incomplet"


@pytest.mark.django_db
def test_transfer_acknowledge_requires_approved_state():
    requester = _make_user("ack_state@test.com")
    membership_create(user=requester, church=ChurchFactory(), is_primary=True)
    transfer = transfer_create(requester=requester, destination_parish=ParishFactory())

    # status == pending → finalisation interdite
    with pytest.raises(ApplicationError):
        transfer_acknowledge(transfer=transfer)


@pytest.mark.django_db
def test_transfer_acknowledge_completes_and_moves_membership():
    # Arrange — origine + destination dotée d'une église.
    requester = _make_user("ack_move@test.com")
    origin_church = ChurchFactory()
    membership_create(user=requester, church=origin_church, is_primary=True)
    destination_church = ChurchFactory(is_main=True)
    destination = destination_church.parish
    transfer = transfer_create(requester=requester, destination_parish=destination)
    transfer_approve(transfer=transfer)

    # Act
    transfer = transfer_acknowledge(transfer=transfer)

    # Assert — statut final + appartenance principale déplacée vers la destination.
    assert transfer.status == TransferStatus.COMPLETED
    primary = Membership.objects.get(user=requester, is_primary=True)
    assert primary.church_id == destination_church.pk
    # Le signal Membership propage la hiérarchie territoriale (miroir primary_parish).
    requester.refresh_from_db()
    assert requester.diocese_id == destination.diocese_id


@pytest.mark.django_db
def test_transfer_acknowledge_fails_when_destination_has_no_church():
    requester = _make_user("ack_nochurch@test.com")
    membership_create(user=requester, church=ChurchFactory(), is_primary=True)
    empty_destination = ParishFactory()  # aucune église créée
    transfer = transfer_create(requester=requester, destination_parish=empty_destination)
    transfer_approve(transfer=transfer)

    with pytest.raises(ApplicationError):
        transfer_acknowledge(transfer=transfer)

"""
Chantier 5a — Dons : domaine, règles RG-PAY, confirmation manuelle (sans IPN).

Étiquetage (B6a/RG-PAY-03), anonymat (RG-PAY-01/02), machine à états
(RG-PAY-04/05), confirmation manuelle cash-only scopée, intentions (B6b).
"""

from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.exceptions import ApplicationError
from apps.donations.models import Donation, DonationStatus
from apps.donations.services import donation_confirm, donation_make
from apps.mass_intentions.services import mass_intention_submit
from apps.org.tests.factories import ChurchFactory, ParishFactory
from apps.users.enums import RoleScope, UserRole
from apps.users.models import RoleAssignment
from apps.users.services_memberships import membership_create
from apps.users.tests.factories import BaseUserFactory


def _donor_primary(church=None):
    donor = BaseUserFactory()
    membership_create(user=donor, church=church or ChurchFactory(), is_primary=True)
    return donor


def _cure(parish, email):
    user = BaseUserFactory(email=email, role=UserRole.PARISH_ADMIN)
    RoleAssignment.objects.create(
        user=user, role=UserRole.PARISH_ADMIN, scope=RoleScope.PARISH,
        parish=parish, is_active=True,
    )
    return user


# ---------------------------------------------------------------------------
# Étiquetage (B6a + RG-PAY-03)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_donation_defaults_to_primary_church_then_overridable():
    church_a = ChurchFactory()
    donor = _donor_primary(church_a)

    # Défaut = église/paroisse principale du donateur.
    d = donation_make(donor=donor, amount=Decimal("1000"), payment_provider="cash")
    assert d.church_id == church_a.id
    assert d.parish_id == church_a.parish_id

    # Surchargeable par church_id explicite.
    church_b = ChurchFactory()
    d2 = donation_make(
        donor=donor, amount=Decimal("1000"), payment_provider="cash", church_id=church_b.id
    )
    assert d2.church_id == church_b.id
    assert d2.parish_id == church_b.parish_id


@pytest.mark.django_db
def test_donation_church_must_match_parish_RG_PAY_03():
    church = ChurchFactory()  # paroisse P1
    other_parish = ParishFactory()  # P2
    donor = BaseUserFactory()

    with pytest.raises(ApplicationError, match="RG-PAY-03"):
        donation_make(
            donor=donor,
            amount=Decimal("1000"),
            payment_provider="cash",
            church_id=church.id,
            parish_id=other_parish.id,
        )


# ---------------------------------------------------------------------------
# Anonymat (RG-PAY-01 + RG-PAY-02)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_anonymous_donor_xor_donor():
    donor = BaseUserFactory()

    # Anonyme → donor NULL + nom anonyme.
    d = donation_make(
        donor=donor,
        amount=Decimal("1000"),
        payment_provider="cash",
        is_anonymous=True,
        anonymous_donor_name="Bienfaiteur",
    )
    assert d.donor_id is None
    assert d.anonymous_donor_name == "Bienfaiteur"

    # Anonyme sans nom → erreur service.
    with pytest.raises(ApplicationError):
        donation_make(
            donor=donor, amount=Decimal("1000"), payment_provider="cash", is_anonymous=True
        )

    # Violation DB directe : donor renseigné ET nom anonyme → IntegrityError (XOR).
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Donation.objects.create(
                donor=donor,
                amount=Decimal("1"),
                payment_provider="cash",
                anonymous_donor_name="X",
                status=DonationStatus.PENDING,
            )


@pytest.mark.django_db
def test_anonymous_donation_max_25000():
    donor = BaseUserFactory()

    with pytest.raises(ApplicationError, match="25 000"):
        donation_make(
            donor=donor,
            amount=Decimal("30000"),
            payment_provider="cash",
            is_anonymous=True,
            anonymous_donor_name="X",
        )

    d = donation_make(
        donor=donor,
        amount=Decimal("25000"),
        payment_provider="cash",
        is_anonymous=True,
        anonymous_donor_name="X",
    )
    assert d.amount == Decimal("25000")


# ---------------------------------------------------------------------------
# Machine à états (RG-PAY-04 + RG-PAY-05)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_donation_created_pending():
    d = donation_make(
        donor=_donor_primary(), amount=Decimal("1000"), payment_provider="cash"
    )
    assert d.status == DonationStatus.PENDING


@pytest.mark.django_db
def test_completed_is_idempotent():
    d = donation_make(
        donor=_donor_primary(), amount=Decimal("1000"), payment_provider="cash"
    )
    donation_confirm(donation=d)
    assert d.status == DonationStatus.CONFIRMED
    again = donation_confirm(donation=d)  # no-op
    assert again.status == DonationStatus.CONFIRMED


@pytest.mark.django_db
def test_terminal_state_not_overwritten():
    d = donation_make(
        donor=_donor_primary(), amount=Decimal("1000"), payment_provider="cash"
    )
    Donation.objects.filter(pk=d.pk).update(status=DonationStatus.FAILED)
    d.refresh_from_db()
    with pytest.raises(ApplicationError):
        donation_confirm(donation=d)


@pytest.mark.django_db
def test_donation_cannot_be_soft_deleted():
    d = donation_make(
        donor=_donor_primary(), amount=Decimal("1000"), payment_provider="cash"
    )
    with pytest.raises(ApplicationError):
        d.delete()
    assert Donation.objects.filter(pk=d.pk).exists()


# ---------------------------------------------------------------------------
# Confirmation manuelle (cash-only, scopée)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_manual_confirm_by_parish_authority_completes():
    church = ChurchFactory()
    parish = church.parish
    donor = _donor_primary(church)
    d = donation_make(donor=donor, amount=Decimal("2000"), payment_provider="cash")
    assert d.parish_id == parish.id and d.status == DonationStatus.PENDING

    client = APIClient()
    client.force_authenticate(_cure(parish, "cure_confirm@test.com"))
    resp = client.post(reverse("api:donations:confirm", kwargs={"donation_id": d.id}))

    assert resp.status_code == 200
    d.refresh_from_db()
    assert d.status == DonationStatus.CONFIRMED


@pytest.mark.django_db
def test_online_provider_not_manually_confirmable():
    church = ChurchFactory()
    donor = _donor_primary(church)
    d = donation_make(donor=donor, amount=Decimal("2000"), payment_provider="wave")

    client = APIClient()
    client.force_authenticate(_cure(church.parish, "cure_online@test.com"))
    resp = client.post(reverse("api:donations:confirm", kwargs={"donation_id": d.id}))

    # Autorité OK mais provider en ligne → refus domaine (400), pas de faux payé.
    assert resp.status_code == 400
    d.refresh_from_db()
    assert d.status == DonationStatus.PENDING


@pytest.mark.django_db
def test_manual_confirm_other_parish_forbidden():
    church = ChurchFactory()
    donor = _donor_primary(church)
    d = donation_make(donor=donor, amount=Decimal("2000"), payment_provider="cash")

    client = APIClient()
    client.force_authenticate(_cure(ParishFactory(), "cure_other@test.com"))  # autre paroisse
    resp = client.post(reverse("api:donations:confirm", kwargs={"donation_id": d.id}))

    assert resp.status_code == 403
    d.refresh_from_db()
    assert d.status == DonationStatus.PENDING


# ---------------------------------------------------------------------------
# Intentions (B6b)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_intention_defaults_to_primary_parish():
    church = ChurchFactory()
    requestor = _donor_primary(church)

    intention = mass_intention_submit(
        requestor=requestor,
        intention_type="for_deceased",
        intention_text="Pour Jean",
    )
    assert intention.parish_id == church.parish_id

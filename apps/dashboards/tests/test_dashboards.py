from decimal import Decimal

import pytest

from apps.dashboards.selectors import cure_dashboard, diocese_dashboard, fidele_dashboard
from apps.donations.services import campaign_create, donation_confirm, donation_make
from apps.org.tests.factories import DioceseFactory, ParishFactory
from apps.users.enums import PastoralRole, RoleScope, UserRole
from apps.users.services_roles import role_assignment_create
from apps.users.tests.factories import BaseUserFactory, ProfileFactory


@pytest.mark.django_db
def test_cure_dashboard_counts_fideles_and_donation_flow():
    # Arrange — une paroisse, 3 fidèles, un curé, une campagne paroissiale + un don
    parish = ParishFactory()
    for _ in range(3):
        ProfileFactory(user=BaseUserFactory(role=UserRole.FIDELE), primary_parish=parish)

    cure = BaseUserFactory(role=UserRole.PARISH_ADMIN, pastoral_role=PastoralRole.PRETRE)
    role_assignment_create(
        user=cure, role=UserRole.PARISH_ADMIN, scope=RoleScope.PARISH,
        parish=parish, is_principal=True,
    )
    campaign = campaign_create(
        created_by=cure, title="Quête du dimanche",
        donation_type="sunday_collection", parish_id=parish.id,
    )
    # Le don est créé PENDING (RG-PAY-04) puis confirmé (espèces) pour entrer au flux.
    donation = donation_make(
        donor=BaseUserFactory(role=UserRole.FIDELE),
        campaign_id=campaign.id, amount=Decimal("5000"), payment_provider="cash",
    )
    donation_confirm(donation=donation)

    # Act
    data = cure_dashboard(parish_id=parish.id)

    # Assert — le curé voit le total de fidèles et le flux de dons de SA paroisse
    assert data["total_fideles"] == 3
    assert data["donation_flow_year"]["total"] == Decimal("5000")
    assert data["donation_flow_year"]["count"] == 1
    assert any(member["is_principal"] for member in data["clergy"])


@pytest.mark.django_db
def test_fidele_dashboard_reports_parish_and_zero_donations():
    # Arrange
    parish = ParishFactory()
    fidele = BaseUserFactory(role=UserRole.FIDELE)
    ProfileFactory(user=fidele, primary_parish=parish)

    # Act
    data = fidele_dashboard(user=fidele)

    # Assert
    assert data["parish"]["id"] == parish.id
    assert data["donations"]["count"] == 0
    assert data["documents"]["total"] == 0


@pytest.mark.django_db
def test_diocese_dashboard_aggregates_parishes_and_fideles():
    # Arrange
    diocese = DioceseFactory()
    p1 = ParishFactory(diocese=diocese)
    ParishFactory(diocese=diocese)
    ProfileFactory(user=BaseUserFactory(role=UserRole.FIDELE), primary_parish=p1)

    # Act
    data = diocese_dashboard(diocese_id=diocese.id)

    # Assert
    assert data["parishes_count"] == 2
    assert data["total_fideles"] == 1

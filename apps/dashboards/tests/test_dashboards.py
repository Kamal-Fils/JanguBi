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


# ---------------------------------------------------------------------------
# Lot 4 — province_dashboard (archevêque) & global_dashboard (super-admin)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_province_dashboard_aggregates_dioceses():
    # Arrange — une province, 2 diocèses, 3 paroisses, 2 fidèles
    from apps.dashboards.selectors import province_dashboard
    from apps.org.tests.factories import ProvinceFactory

    province = ProvinceFactory()
    d1 = DioceseFactory(province=province)
    d2 = DioceseFactory(province=province)
    p1 = ParishFactory(diocese=d1)
    ParishFactory(diocese=d1)
    ParishFactory(diocese=d2)
    ProfileFactory(user=BaseUserFactory(role=UserRole.FIDELE), primary_parish=p1)
    ProfileFactory(user=BaseUserFactory(role=UserRole.FIDELE), primary_parish=p1)

    # Act
    data = province_dashboard(province_id=province.id)

    # Assert
    assert data["province"]["id"] == province.id
    assert data["dioceses_count"] == 2
    assert data["parishes_count"] == 3
    assert data["total_fideles"] == 2
    rows = {row["id"]: row for row in data["dioceses"]}
    assert rows[d1.id]["parishes_count"] == 2
    assert rows[d1.id]["fideles_count"] == 2
    assert rows[d2.id]["parishes_count"] == 1


@pytest.mark.django_db
def test_my_province_api_for_archeveque():
    # Arrange — archevêque rattaché à sa province via RoleAssignment
    from django.urls import reverse
    from rest_framework.test import APIClient

    from apps.org.tests.factories import ProvinceFactory

    province = ProvinceFactory()
    DioceseFactory(province=province)
    archeveque = BaseUserFactory(
        role=UserRole.PROVINCE_ADMIN, pastoral_role=PastoralRole.ARCHEVEQUE
    )
    role_assignment_create(
        user=archeveque, role=UserRole.PROVINCE_ADMIN, scope=RoleScope.PROVINCE,
        province=province,
    )
    client = APIClient()
    client.force_authenticate(user=archeveque)

    # Act
    response = client.get(reverse("api:dashboards:my-province"))

    # Assert
    assert response.status_code == 200
    assert response.data["province"]["id"] == province.id
    assert response.data["dioceses_count"] == 1


@pytest.mark.django_db
def test_global_dashboard_api_super_admin_only():
    from django.urls import reverse
    from rest_framework.test import APIClient

    from apps.users.tests.factories import SuperAdminFactory

    url = reverse("api:dashboards:global")

    # Un fidèle est refusé
    fidele_client = APIClient()
    fidele_client.force_authenticate(user=BaseUserFactory(role=UserRole.FIDELE))
    assert fidele_client.get(url).status_code == 403

    # Le super-admin voit les compteurs plateforme
    admin_client = APIClient()
    admin_client.force_authenticate(user=SuperAdminFactory())
    response = admin_client.get(url)
    assert response.status_code == 200
    assert response.data["users_total"] >= 2
    assert "pending_clergy_invitations" in response.data
    assert "donations_total_year" in response.data

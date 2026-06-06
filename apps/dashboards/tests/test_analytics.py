from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.dashboards.analytics import resolve_analytics_context
from apps.donations.services import campaign_create, donation_confirm, donation_make
from apps.org.tests.factories import (
    DioceseFactory,
    ParishFactory,
    ProvinceFactory,
)
from apps.users.enums import PastoralRole, RoleScope, UserRole
from apps.users.services_roles import role_assignment_create
from apps.users.tests.factories import BaseUserFactory


def _confirmed_donation(*, cure, parish, amount, donation_type="sunday_collection"):
    campaign = campaign_create(
        created_by=cure,
        title=f"Campagne {donation_type}",
        donation_type=donation_type,
        parish_id=parish.id,
    )
    d = donation_make(
        donor=BaseUserFactory(role=UserRole.FIDELE),
        campaign_id=campaign.id,
        amount=Decimal(amount),
        payment_provider="cash",
    )
    donation_confirm(donation=d)
    return d


@pytest.mark.django_db
def test_resolve_context_levels_by_role():
    province = ProvinceFactory()
    diocese = DioceseFactory(province=province)
    parish = ParishFactory(diocese=diocese)

    cure = BaseUserFactory(role=UserRole.PARISH_ADMIN, pastoral_role=PastoralRole.PRETRE)
    role_assignment_create(
        user=cure, role=UserRole.PARISH_ADMIN, scope=RoleScope.PARISH,
        parish=parish, is_principal=True,
    )
    eveque = BaseUserFactory(role=UserRole.DIOCESE_ADMIN, pastoral_role=PastoralRole.EVEQUE)
    role_assignment_create(
        user=eveque, role=UserRole.DIOCESE_ADMIN, scope=RoleScope.DIOCESE, diocese=diocese,
    )
    archeveque = BaseUserFactory(role=UserRole.PROVINCE_ADMIN, pastoral_role=PastoralRole.ARCHEVEQUE)
    role_assignment_create(
        user=archeveque, role=UserRole.PROVINCE_ADMIN, scope=RoleScope.PROVINCE, province=province,
    )

    assert resolve_analytics_context(cure)["level"] == "parish"
    assert resolve_analytics_context(eveque)["level"] == "diocese"
    assert resolve_analytics_context(archeveque)["level"] == "province"
    # Un fidèle n'a aucune autorité territoriale → pas d'analytique scopée.
    assert resolve_analytics_context(BaseUserFactory(role=UserRole.FIDELE)) is None


@pytest.mark.django_db
def test_analytics_api_diocese_scoped_and_ranked():
    province = ProvinceFactory()
    diocese = DioceseFactory(province=province)
    other_diocese = DioceseFactory(province=province)
    parish_a = ParishFactory(diocese=diocese, name="Paroisse A")
    parish_other = ParishFactory(diocese=other_diocese, name="Hors diocèse")

    cure = BaseUserFactory(role=UserRole.PARISH_ADMIN, pastoral_role=PastoralRole.PRETRE)
    _confirmed_donation(cure=cure, parish=parish_a, amount="10000")
    _confirmed_donation(cure=cure, parish=parish_other, amount="99999")  # hors scope

    eveque = BaseUserFactory(role=UserRole.DIOCESE_ADMIN, pastoral_role=PastoralRole.EVEQUE)
    role_assignment_create(
        user=eveque, role=UserRole.DIOCESE_ADMIN, scope=RoleScope.DIOCESE, diocese=diocese,
    )
    client = APIClient()
    client.force_authenticate(user=eveque)

    resp = client.get("/api/v1/dashboards/analytics/")

    assert resp.status_code == 200
    assert resp.data["level"] == "diocese"
    assert resp.data["ranking_level"] == "parish"
    # Borné au diocèse : on voit les 10000 de la paroisse A, PAS les 99999 hors scope.
    assert resp.data["kpis"]["donations_total"] == 10000
    names = {r["name"] for r in resp.data["ranking"]}
    assert "Paroisse A" in names
    assert "Hors diocèse" not in names


@pytest.mark.django_db
def test_analytics_api_forbidden_for_fidele():
    client = APIClient()
    client.force_authenticate(user=BaseUserFactory(role=UserRole.FIDELE))
    resp = client.get("/api/v1/dashboards/analytics/")
    assert resp.status_code == 403

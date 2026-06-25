"""Tests API apps/spiritual — /api/v1/spiritual/reflections/* (fix du 404 live)."""

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.org.tests.factories import ChurchFactory, ParishFactory
from apps.spiritual.models import PastoralReflection
from apps.users.enums import PastoralRole, RoleScope, UserRole
from apps.users.models import RoleAssignment
from apps.users.services_memberships import membership_create
from apps.users.tests.factories import BaseUserFactory

TODAY_URL = "/api/v1/spiritual/reflections/today/"
LIST_URL = "/api/v1/spiritual/reflections/"


def _parish_priest(parish):
    user = BaseUserFactory(pastoral_role=PastoralRole.PRETRE)
    RoleAssignment.objects.create(
        user=user, role=UserRole.PARISH_ADMIN, scope=RoleScope.PARISH,
        parish=parish, is_active=True,
    )
    return user


@pytest.mark.django_db
def test_today_route_exists_and_returns_200_null_when_none():
    client = APIClient()
    client.force_authenticate(user=BaseUserFactory())

    resp = client.get(TODAY_URL)

    # Avant ce fix : 404 (route absente). Désormais : 200 + null si aucune réflexion.
    assert resp.status_code == 200
    assert resp.data is None


@pytest.mark.django_db
def test_today_returns_parish_reflection_for_member():
    church = ChurchFactory()
    parish = church.parish
    priest = _parish_priest(parish)
    PastoralReflection.objects.create(
        author=priest, reflection_date=timezone.localdate(),
        content="Paix et joie.", scope_type="parish", scope_parish=parish,
    )
    fidele = BaseUserFactory()
    membership_create(user=fidele, church=church, is_primary=True)

    client = APIClient()
    client.force_authenticate(user=fidele)
    resp = client.get(TODAY_URL)

    assert resp.status_code == 200
    assert resp.data["content"] == "Paix et joie."


@pytest.mark.django_db
def test_post_create_forbidden_for_fidele():
    parish = ParishFactory()
    client = APIClient()
    client.force_authenticate(user=BaseUserFactory())

    resp = client.post(
        LIST_URL,
        {"content": "x", "scope_type": "parish", "scope_parish_id": parish.id},
        format="json",
    )

    assert resp.status_code == 403


@pytest.mark.django_db
def test_post_create_succeeds_for_priest():
    parish = ParishFactory()
    priest = _parish_priest(parish)
    client = APIClient()
    client.force_authenticate(user=priest)

    resp = client.post(
        LIST_URL,
        {"content": "Aimez-vous les uns les autres.", "scope_type": "parish", "scope_parish_id": parish.id},
        format="json",
    )

    assert resp.status_code == 201
    assert resp.data["content"] == "Aimez-vous les uns les autres."
    assert resp.data["scope_parish_id"] == parish.id


@pytest.mark.django_db
def test_my_today_returns_authors_own():
    parish = ParishFactory()
    priest = _parish_priest(parish)
    PastoralReflection.objects.create(
        author=priest, reflection_date=timezone.localdate(),
        content="Ma méditation.", scope_type="parish", scope_parish=parish,
    )

    client = APIClient()
    client.force_authenticate(user=priest)
    resp = client.get("/api/v1/spiritual/reflections/my-today/")

    assert resp.status_code == 200
    assert resp.data["content"] == "Ma méditation."

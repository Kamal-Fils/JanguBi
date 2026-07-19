"""GET /api/v1/users/{id}/ — non-régression sérialisation + pagination d'audit.

`UserDetailApi.get_user_profile` émettait `primary_parish` en instance ORM brute :
le renderer JSON de DRF plantait → **500 pour tout fidèle onboardé** (même bug que
BUG-B1 côté liste, cf. test_users_list_api.py). Doit être {id, name} | null.
"""

import pytest
from rest_framework.test import APIClient

from apps.org.tests.factories import ParishFactory
from apps.users.enums import AuditEvent
from apps.users.models import SecurityAuditLog
from apps.users.tests.factories import (
    BaseUserFactory,
    ProfileFactory,
    SuperAdminFactory,
)


def _admin_client():
    client = APIClient()
    client.force_authenticate(user=SuperAdminFactory())
    return client


@pytest.mark.django_db
def test_user_detail_serializes_primary_parish_as_object():
    # Arrange
    parish = ParishFactory(name="Cathédrale du Souvenir")
    fidele = BaseUserFactory()
    ProfileFactory(user=fidele, primary_parish=parish)

    # Act
    resp = _admin_client().get(f"/api/v1/users/{fidele.id}/")

    # Assert — ROUGE avant le fix : 500 (Parish non sérialisable au rendu JSON).
    assert resp.status_code == 200
    assert resp.data["user_profile"]["primary_parish"] == {
        "id": parish.id,
        "name": parish.name,
    }


@pytest.mark.django_db
def test_user_detail_primary_parish_null_when_absent():
    # Arrange
    user = BaseUserFactory()
    ProfileFactory(user=user)  # profil sans paroisse principale

    # Act
    resp = _admin_client().get(f"/api/v1/users/{user.id}/")

    # Assert
    assert resp.status_code == 200
    assert resp.data["user_profile"]["primary_parish"] is None


@pytest.mark.django_db
def test_user_detail_returns_404_for_unknown_user():
    resp = _admin_client().get("/api/v1/users/00000000-0000-0000-0000-000000000000/")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Journal d'audit — pagination
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_audit_log_endpoint_is_paginated():
    # Sans pagination, un compte ancien renvoyait TOUS ses logs d'un bloc
    # (risque de timeout / OOM).
    # Arrange
    user = BaseUserFactory()
    for _ in range(7):
        SecurityAuditLog.objects.create(user=user, event=AuditEvent.LOGIN)

    # Act
    resp = _admin_client().get(f"/api/v1/users/{user.id}/audit-logs/?limit=3&offset=0")

    # Assert
    assert resp.status_code == 200
    assert resp.data["count"] == 7
    assert len(resp.data["results"]) == 3
    assert resp.data["limit"] == 3

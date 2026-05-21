"""
Tests des APIs errors — sécurité post-refactoring.

Vérifie que :
- TriggerErrorApi et TriggerUnhandledExceptionApi exigent authentification (401)
- Seuls les super_admin peuvent y accéder (403 pour les autres rôles)

Ces tests couvrent la correction CRITICAL : suppression de TriggerValidateUniqueErrorApi
(qui créait des utilisateurs réels sans authentification) et ajout de IsSuperAdmin
sur les endpoints restants.
"""

import pytest
from rest_framework.test import APIClient

from apps.users.tests.factories import BaseUserFactory, StaffUserFactory, SuperAdminFactory

_TRIGGER_URL = "/api/v1/errors/trigger/"
_EXCEPTION_URL = "/api/v1/errors/trigger/exception/"


@pytest.fixture
def anon_client():
    return APIClient()


@pytest.fixture
def fidele_client():
    client = APIClient()
    client.force_authenticate(user=BaseUserFactory())
    return client


@pytest.fixture
def staff_client():
    client = APIClient()
    client.force_authenticate(user=StaffUserFactory())
    return client


@pytest.fixture
def super_admin_client():
    client = APIClient()
    client.force_authenticate(user=SuperAdminFactory())
    return client


# ---------------------------------------------------------------------------
# TriggerErrorApi (GET /api/v1/errors/trigger/)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_trigger_error_returns_401_for_unauthenticated(anon_client):
    response = anon_client.get(_TRIGGER_URL)
    assert response.status_code == 401


@pytest.mark.django_db
def test_trigger_error_returns_403_for_fidele(fidele_client):
    response = fidele_client.get(_TRIGGER_URL)
    assert response.status_code == 403


@pytest.mark.django_db
def test_trigger_error_returns_403_for_parish_admin(staff_client):
    response = staff_client.get(_TRIGGER_URL)
    assert response.status_code == 403


@pytest.mark.django_db
def test_trigger_error_returns_200_for_super_admin(super_admin_client):
    response = super_admin_client.get(_TRIGGER_URL)
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# TriggerUnhandledExceptionApi (GET /api/v1/errors/trigger/exception/)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_trigger_exception_returns_401_for_unauthenticated(anon_client):
    response = anon_client.get(_EXCEPTION_URL)
    assert response.status_code == 401


@pytest.mark.django_db
def test_trigger_exception_returns_403_for_fidele(fidele_client):
    response = fidele_client.get(_EXCEPTION_URL)
    assert response.status_code == 403


@pytest.mark.django_db
def test_trigger_exception_returns_403_for_parish_admin(staff_client):
    response = staff_client.get(_EXCEPTION_URL)
    assert response.status_code == 403


@pytest.mark.django_db
def test_trigger_exception_raises_for_super_admin(super_admin_client):
    # The endpoint intentionally raises an unhandled exception — expect 500
    response = super_admin_client.get(_EXCEPTION_URL)
    assert response.status_code == 500

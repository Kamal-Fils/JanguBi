"""
Tests unitaires — services d'authentification.

Couvre :
  - auth_logout : crée un SecurityAuditLog LOGOUT (happy path)
  - auth_logout : résilience si l'audit échoue (ne lève pas d'exception)
  - auth_logout_all_devices : crée un SecurityAuditLog LOGOUT avec metadata
  - auth_logout_all_devices : le jwt_key est rotatif après l'appel
  - auth_logout_all_devices : résilience si l'audit échoue
"""

import uuid
from unittest.mock import patch

import pytest

from apps.authentication.services import auth_logout, auth_logout_all_devices
from apps.users.enums import AuditEvent
from apps.users.models import SecurityAuditLog
from apps.users.tests.factories import BaseUserFactory

# ---------------------------------------------------------------------------
# auth_logout
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_auth_logout_creates_audit_log():
    # Arrange
    user = BaseUserFactory()

    # Act
    auth_logout(user, ip="192.168.1.1")

    # Assert
    assert SecurityAuditLog.objects.filter(
        user=user,
        event=AuditEvent.LOGOUT,
        ip_address="192.168.1.1",
    ).exists()


@pytest.mark.django_db
def test_auth_logout_without_ip_creates_audit_log():
    # Arrange
    user = BaseUserFactory()

    # Act
    auth_logout(user, ip=None)

    # Assert
    log = SecurityAuditLog.objects.get(user=user, event=AuditEvent.LOGOUT)
    assert log.ip_address is None


@pytest.mark.django_db
def test_auth_logout_is_resilient_when_audit_write_fails():
    """
    Si la création du SecurityAuditLog lève une exception (ex: contrainte DB),
    auth_logout ne doit pas propager l'erreur — il log simplement et continue.
    """
    # Arrange
    user = BaseUserFactory()

    # Act & Assert — aucune exception ne doit remonter
    with patch(
        "apps.authentication.services.SecurityAuditLog.objects.create",
        side_effect=Exception("DB error simulée"),
    ):
        auth_logout(user, ip="10.0.0.1")


# ---------------------------------------------------------------------------
# auth_logout_all_devices
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_auth_logout_all_devices_rotates_jwt_key():
    # Arrange
    user = BaseUserFactory()
    original_jwt_key = user.jwt_key

    # Act
    auth_logout_all_devices(user, ip="10.0.0.1")

    # Assert
    user.refresh_from_db()
    assert user.jwt_key != original_jwt_key
    assert isinstance(user.jwt_key, uuid.UUID)


@pytest.mark.django_db
def test_auth_logout_all_devices_creates_audit_log_with_scope_metadata():
    # Arrange
    user = BaseUserFactory()

    # Act
    auth_logout_all_devices(user, ip="10.0.0.2")

    # Assert
    log = SecurityAuditLog.objects.get(
        user=user,
        event=AuditEvent.LOGOUT,
    )
    assert log.metadata.get("scope") == "all_devices"
    assert log.ip_address == "10.0.0.2"


@pytest.mark.django_db
def test_auth_logout_all_devices_jwt_key_is_valid_new_uuid():
    """Le jwt_key rotatif doit être un UUID v4 valide différent de l'original."""
    # Arrange
    user = BaseUserFactory()
    key_before = str(user.jwt_key)

    # Act
    auth_logout_all_devices(user)

    # Assert
    user.refresh_from_db()
    key_after = str(user.jwt_key)
    assert key_before != key_after
    uuid.UUID(key_after)  # lève ValueError si le format UUID est invalide


@pytest.mark.django_db
def test_auth_logout_all_devices_is_resilient_when_audit_write_fails():
    """
    Si la création du SecurityAuditLog lève une exception,
    auth_logout_all_devices ne doit pas propager l'erreur.
    Le jwt_key doit quand même avoir été rotatif avant l'échec de l'audit.
    """
    # Arrange
    user = BaseUserFactory()
    original_jwt_key = user.jwt_key

    # Act & Assert — aucune exception ne doit remonter
    with patch(
        "apps.authentication.services.SecurityAuditLog.objects.create",
        side_effect=Exception("DB error simulée"),
    ):
        auth_logout_all_devices(user, ip="172.16.0.1")

    # Le jwt_key doit avoir été rotatif malgré l'échec de l'audit
    user.refresh_from_db()
    assert user.jwt_key != original_jwt_key

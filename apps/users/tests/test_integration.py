"""
Tests d'intégration — flux complets end-to-end (sans mock sauf email/token).

Stratégie :
  - Cache : LocMemCache (pas de Redis réel)
  - Emails : _send_email_safe mocké pour éviter SMTP
  - DB : TestCase (transaction rollback entre tests)

Flux testés :
  1. Inscription fidèle → activation email
  2. Anti-replay : impossible d'activer deux fois avec le même token
  3. Mot de passe oublié → réinitialisation complète
  4. Changement de mot de passe (sudo mode)
  5. Changement d'email (OTP complet) → réversion
  6. Cycle de vie du compte (désactivation / réactivation / soft delete)
"""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.core.exceptions import ApplicationError, TokenInvalidError
from apps.users.enums import AuditEvent, UserRole
from apps.users.models import BaseUser, SecurityAuditLog
from apps.users.otp import (
    RESET_TOKEN_TTL,
    VERIFY_TOKEN_TTL,
    generate_url_token,
    otp_store,
    token_store,
)
from apps.users.services import (
    email_change_confirm,
    email_change_request,
    email_change_revert,
    password_change,
    password_reset_confirm,
    password_reset_request,
    user_activate_account,
    user_register_fidele,
    user_soft_delete,
    user_toggle_active,
)
from apps.users.tests.factories import AdminUserFactory, BaseUserFactory

PATCH_EMAIL = "apps.users.services._send_email_safe"
PATCH_DELAY = "apps.users.services._dummy_delay"

INTEGRATION_SETTINGS = {
    "CACHES": {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
    },
    "FRONTEND_URL": "http://localhost:3000",
}


@override_settings(**INTEGRATION_SETTINGS)
class RegistrationActivationFlowTests(TestCase):
    """Flow 1 : inscription fidèle → email de vérification → activation."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    @patch(PATCH_EMAIL)
    def test_full_registration_and_activation(self, mock_email):
        # Arrange
        with patch("apps.users.services.token_store"):
            user = user_register_fidele(
                email="alice@example.com",
                phone_number="+221771111111",
                password="StrongPassw0rd!",
                first_name="Alice",
                last_name="Dupont",
                title="MRS",
            )

        self.assertFalse(user.is_active)
        self.assertFalse(user.is_verified)
        self.assertEqual(user.role, UserRole.FIDELE)

        # Act — simulation du clic sur le lien email
        token = generate_url_token()
        token_store("email_verify", token, {"user_id": user.id}, ttl=VERIFY_TOKEN_TTL)
        activated = user_activate_account(token=token)

        # Assert
        self.assertTrue(activated.is_active)
        self.assertTrue(activated.is_verified)
        user.refresh_from_db()
        self.assertTrue(user.is_active)

        events = list(SecurityAuditLog.objects.filter(user=user).values_list("event", flat=True))
        self.assertIn(AuditEvent.REGISTER, events)
        self.assertIn(AuditEvent.EMAIL_VERIFIED, events)

    @patch(PATCH_EMAIL)
    def test_cannot_activate_twice_with_same_token(self, mock_email):
        # Arrange
        with patch("apps.users.services.token_store"):
            user = user_register_fidele(
                email="bob@example.com",
                phone_number="+221772222222",
                password="StrongPassw0rd!",
                first_name="Bob",
                last_name="Martin",
                title="MR",
            )

        token = generate_url_token()
        token_store("email_verify", token, {"user_id": user.id}, ttl=VERIFY_TOKEN_TTL)
        user_activate_account(token=token)

        # Act & Assert — second usage du même token → anti-replay
        with self.assertRaises(TokenInvalidError):
            user_activate_account(token=token)


@override_settings(**INTEGRATION_SETTINGS)
class PasswordResetFlowTests(TestCase):
    """Flow 3 : mot de passe oublié → lien magique → nouveau mot de passe."""

    def setUp(self):
        cache.clear()
        self.user = BaseUserFactory(email="user@example.com", password="OldPassw0rd!")

    def tearDown(self):
        cache.clear()

    @patch(PATCH_EMAIL)
    def test_full_password_reset_flow(self, mock_email):
        # Arrange
        password_reset_request(email="user@example.com", ip="1.2.3.4")
        old_jwt_key = self.user.jwt_key

        token = generate_url_token()
        token_store("pwd_reset", token, {"user_id": self.user.id}, ttl=RESET_TOKEN_TTL)

        # Act
        password_reset_confirm(token=token, new_password="NewStrongPassw0rd!")

        # Assert
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewStrongPassw0rd!"))
        self.assertFalse(self.user.check_password("OldPassw0rd!"))
        self.assertNotEqual(self.user.jwt_key, old_jwt_key)

    @patch(PATCH_DELAY)
    def test_anti_enumeration_unknown_email_returns_silently(self, mock_delay):
        # Act — ne doit pas lever d'exception même si l'email est inconnu
        password_reset_request(email="nobody@example.com", ip="1.2.3.4")
        mock_delay.assert_called_once()


@override_settings(**INTEGRATION_SETTINGS)
class PasswordChangeFlowTests(TestCase):
    """Flow 4 : changement de mot de passe (sudo mode)."""

    def setUp(self):
        cache.clear()
        self.user = BaseUserFactory(password="CurrentPassw0rd!")

    def tearDown(self):
        cache.clear()

    @patch(PATCH_EMAIL)
    def test_full_password_change_rotates_jwt_key(self, mock_email):
        # Arrange
        old_key = self.user.jwt_key

        # Act
        password_change(
            user=self.user,
            current_password="CurrentPassw0rd!",
            new_password="NewPassw0rd!",
        )

        # Assert
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewPassw0rd!"))
        self.assertNotEqual(self.user.jwt_key, old_key)

    def test_wrong_current_password_does_not_change_password(self):
        with self.assertRaises(ApplicationError):
            password_change(
                user=self.user,
                current_password="WrongPassword!",
                new_password="NewPassw0rd!",
            )
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("CurrentPassw0rd!"))


@override_settings(**INTEGRATION_SETTINGS)
class EmailChangeFlowTests(TestCase):
    """Flow 5 : changement d'email avec OTP + notification + réversion."""

    def setUp(self):
        cache.clear()
        self.user = BaseUserFactory(email="original@example.com", password="GoodPassw0rd!")

    def tearDown(self):
        cache.clear()

    @patch(PATCH_EMAIL)
    def test_full_email_change_flow(self, mock_email):
        # Arrange
        old_key = self.user.jwt_key

        email_change_request(
            user=self.user,
            new_email="newaddress@example.com",
            current_password="GoodPassw0rd!",
        )
        pending = cache.get(f"email_change_pending:{self.user.id}")
        self.assertEqual(pending, "newaddress@example.com")

        # Réinitialise le cache pour contrôler l'OTP
        cache.clear()
        otp_store(self.user.id, "email_change", "654321")
        cache.set(f"email_change_pending:{self.user.id}", "newaddress@example.com", timeout=600)

        # Act
        email_change_confirm(user=self.user, otp_code="654321")

        # Assert
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "newaddress@example.com")
        self.assertNotEqual(self.user.jwt_key, old_key)

    def test_email_change_revert_restores_original_and_invalidates_password(self):
        # Arrange — simule un changement malveillant
        self.user.email = "hacked@example.com"
        self.user.save(update_fields=["email", "updated_at"])

        revert_token = generate_url_token()
        token_store(
            "email_revert",
            revert_token,
            {"user_id": self.user.id, "old_email": "original@example.com"},
            ttl=604800,
        )

        # Act
        email_change_revert(token=revert_token)

        # Assert
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "original@example.com")
        self.assertFalse(self.user.has_usable_password())

    def test_revert_token_consumed_anti_replay(self):
        # Arrange
        self.user.email = "hacked@example.com"
        self.user.save(update_fields=["email", "updated_at"])

        revert_token = generate_url_token()
        token_store(
            "email_revert",
            revert_token,
            {"user_id": self.user.id, "old_email": "original@example.com"},
            ttl=604800,
        )
        email_change_revert(token=revert_token)

        # Act & Assert — second usage impossible
        with self.assertRaises(TokenInvalidError):
            email_change_revert(token=revert_token)


@override_settings(**INTEGRATION_SETTINGS)
class AccountLifecycleTests(TestCase):
    """Flow 6 : cycle de vie complet d'un compte."""

    def setUp(self):
        cache.clear()
        self.admin = AdminUserFactory()

    def tearDown(self):
        cache.clear()

    def test_toggle_deactivate_then_reactivate(self):
        # Arrange
        user = BaseUserFactory()

        # Act & Assert — désactivation
        user_toggle_active(user=user, is_active=False, performed_by=self.admin)
        user.refresh_from_db()
        self.assertFalse(user.is_active)

        # Act & Assert — réactivation
        user_toggle_active(user=user, is_active=True, performed_by=self.admin)
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_soft_delete_anonymises_email_and_deactivates(self):
        # Arrange
        user = BaseUserFactory(email="victim@example.com")
        original_id = user.id

        # Act
        user_soft_delete(user=user, performed_by=self.admin)

        # Assert
        db_user = BaseUser.objects.get(id=original_id)
        self.assertFalse(db_user.is_active)
        self.assertNotIn("victim", db_user.email)
        self.assertFalse(
            BaseUser.objects.filter(email__iexact="victim@example.com").exists()
        )

    def test_audit_trail_survives_soft_delete(self):
        # Arrange
        user = BaseUserFactory()

        # Act
        user_soft_delete(user=user, performed_by=self.admin)

        # Assert
        self.assertTrue(SecurityAuditLog.objects.filter(user=user).exists())

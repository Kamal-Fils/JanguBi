"""
Tests unitaires — changement d'email (flow OTP complet).

Couvre :
  - email_change_request : sudo mode, même email, email déjà pris, OTP envoyé
  - email_change_confirm : OTP valide, OTP invalide, session expirée, rotation jwt_key
  - email_change_revert : token valide, token invalide, email déjà restauré
"""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.core.exceptions import ApplicationError, TokenInvalidError
from apps.users.otp import (
    REVERT_TOKEN_TTL,
    generate_url_token,
    otp_store,
    token_store,
)
from apps.users.services import email_change_confirm, email_change_request, email_change_revert
from apps.users.tests.factories import BaseUserFactory

PATCH_EMAIL = "apps.users.services._send_email_safe"
PATCH_OTP_STORE = "apps.users.services.otp_store"
PATCH_OTP_VERIFY = "apps.users.services.otp_verify"

CACHE_SETTINGS = {
    "CACHES": {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
}


@override_settings(**CACHE_SETTINGS)
class EmailChangeRequestTests(TestCase):

    def setUp(self):
        cache.clear()
        self.user = BaseUserFactory(email="old@example.com", password="GoodPassw0rd!")

    def tearDown(self):
        cache.clear()

    @patch(PATCH_EMAIL)
    @patch(PATCH_OTP_STORE)
    def test_happy_path_sends_otp(self, mock_store, mock_email):
        email_change_request(
            user=self.user,
            new_email="new@example.com",
            current_password="GoodPassw0rd!",
        )
        mock_store.assert_called_once()
        mock_email.assert_called_once()
        args, _ = mock_email.call_args
        self.assertEqual(args[0], "email_change_otp")
        self.assertEqual(args[2], "new@example.com")  # Envoyé à la NOUVELLE adresse

    @patch(PATCH_EMAIL)
    @patch(PATCH_OTP_STORE)
    def test_otp_sent_to_new_email_not_old(self, mock_store, mock_email):
        email_change_request(
            user=self.user,
            new_email="new@example.com",
            current_password="GoodPassw0rd!",
        )
        _, kwargs = mock_email.call_args
        target = mock_email.call_args[0][2]
        self.assertNotEqual(target, "old@example.com")

    def test_wrong_password_raises(self):
        with self.assertRaises(ApplicationError) as ctx:
            email_change_request(
                user=self.user,
                new_email="new@example.com",
                current_password="WrongPass!",
            )
        self.assertIn("incorrect", str(ctx.exception).lower())

    def test_same_email_raises(self):
        with self.assertRaises(ApplicationError) as ctx:
            email_change_request(
                user=self.user,
                new_email="old@example.com",
                current_password="GoodPassw0rd!",
            )
        self.assertIn("identique", str(ctx.exception))

    def test_email_already_taken_raises(self):
        BaseUserFactory(email="taken@example.com")
        with self.assertRaises(ApplicationError) as ctx:
            email_change_request(
                user=self.user,
                new_email="taken@example.com",
                current_password="GoodPassw0rd!",
            )
        self.assertIn("déjà utilisée", str(ctx.exception))

    @patch(PATCH_EMAIL)
    def test_new_email_stored_in_redis(self, mock_email):
        with patch(PATCH_OTP_STORE):
            email_change_request(
                user=self.user,
                new_email="new@example.com",
                current_password="GoodPassw0rd!",
            )
        pending = cache.get(f"email_change_pending:{self.user.id}")
        self.assertEqual(pending, "new@example.com")


@override_settings(**CACHE_SETTINGS)
class EmailChangeConfirmTests(TestCase):

    def setUp(self):
        cache.clear()
        self.user = BaseUserFactory(email="old@example.com")
        # Prépare l'état : OTP stocké + new_email en session Redis
        otp_store(self.user.id, "email_change", "123456")
        cache.set(f"email_change_pending:{self.user.id}", "new@example.com", timeout=600)

    def tearDown(self):
        cache.clear()

    @patch(PATCH_EMAIL)
    def test_happy_path_changes_email(self, mock_email):
        email_change_confirm(user=self.user, otp_code="123456")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new@example.com")

    @patch(PATCH_EMAIL)
    def test_rotates_jwt_key(self, mock_email):
        old_key = self.user.jwt_key
        email_change_confirm(user=self.user, otp_code="123456")
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.jwt_key, old_key)

    @patch(PATCH_EMAIL)
    def test_notification_sent_to_old_email(self, mock_email):
        email_change_confirm(user=self.user, otp_code="123456")
        # L'email de notification doit être envoyé à l'ANCIENNE adresse
        mock_email.assert_called_once()
        args, _ = mock_email.call_args
        self.assertEqual(args[0], "email_change_notification")
        self.assertEqual(args[2], "old@example.com")

    def test_wrong_otp_raises(self):
        with self.assertRaises(Exception):  # OtpInvalidError ou OtpLockedError
            email_change_confirm(user=self.user, otp_code="000000")

    def test_expired_session_raises(self):
        cache.delete(f"email_change_pending:{self.user.id}")
        with self.assertRaises(ApplicationError) as ctx:
            email_change_confirm(user=self.user, otp_code="123456")
        self.assertIn("expirée", str(ctx.exception))

    @patch(PATCH_EMAIL)
    def test_revert_token_stored_after_confirm(self, mock_email):
        with patch("apps.users.services.token_store") as mock_token:
            email_change_confirm(user=self.user, otp_code="123456")
        # Un token de réversion doit être stocké
        calls = [c[0][0] for c in mock_token.call_args_list]
        self.assertIn("email_revert", calls)

    @patch(PATCH_EMAIL)
    def test_race_condition_email_taken(self, mock_email):
        """Si la nouvelle email est prise entre la requête et la confirmation."""
        BaseUserFactory(email="new@example.com")
        with self.assertRaises(ApplicationError) as ctx:
            email_change_confirm(user=self.user, otp_code="123456")
        self.assertIn("prise", str(ctx.exception))


@override_settings(**CACHE_SETTINGS)
class EmailChangeRevertTests(TestCase):

    def setUp(self):
        cache.clear()
        self.user = BaseUserFactory(email="new@example.com")
        self.revert_token = generate_url_token()
        token_store(
            "email_revert",
            self.revert_token,
            {"user_id": self.user.id, "old_email": "original@example.com"},
            ttl=REVERT_TOKEN_TTL,
        )

    def tearDown(self):
        cache.clear()

    def test_restores_old_email(self):
        email_change_revert(token=self.revert_token)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "original@example.com")

    def test_sets_unusable_password(self):
        email_change_revert(token=self.revert_token)
        self.user.refresh_from_db()
        self.assertFalse(self.user.has_usable_password())

    def test_rotates_jwt_key(self):
        old_key = self.user.jwt_key
        email_change_revert(token=self.revert_token)
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.jwt_key, old_key)

    def test_invalid_token_raises(self):
        with self.assertRaises(TokenInvalidError):
            email_change_revert(token="bad_token")

    def test_token_consumed_anti_replay(self):
        email_change_revert(token=self.revert_token)
        with self.assertRaises(TokenInvalidError):
            email_change_revert(token=self.revert_token)

    def test_idempotent_if_email_not_changed(self):
        """Si l'email est déjà l'ancienne (ex : double clic sur le lien), pas d'erreur."""
        self.user.email = "original@example.com"
        self.user.save(update_fields=["email", "updated_at"])
        # Ne doit pas lever d'exception
        result = email_change_revert(token=self.revert_token)
        self.assertEqual(result.email, "original@example.com")

    def test_unknown_user_raises(self):
        bad_token = generate_url_token()
        token_store(
            "email_revert",
            bad_token,
            {"user_id": 999999, "old_email": "x@x.com"},
            ttl=REVERT_TOKEN_TTL,
        )
        with self.assertRaises(TokenInvalidError):
            email_change_revert(token=bad_token)

    def test_old_email_taken_raises(self):
        BaseUserFactory(email="original@example.com")
        with self.assertRaises(ApplicationError):
            email_change_revert(token=self.revert_token)

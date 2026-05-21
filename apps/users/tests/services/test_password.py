"""
Tests unitaires — changement et réinitialisation de mot de passe.

Couvre :
  - password_change : sudo mode, même MDP, MDP faible, rotation jwt_key
  - password_reset_request : utilisateur existant, anti-énumération, rate limit
  - password_reset_confirm : token valide, token invalide, rotation jwt_key
"""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.core.exceptions import ApplicationError, OtpRateLimitError, TokenInvalidError
from apps.users.otp import RESET_TOKEN_TTL, generate_url_token, token_get, token_store
from apps.users.services import password_change, password_reset_confirm, password_reset_request
from apps.users.tests.factories import BaseUserFactory, InactiveUserFactory

PATCH_EMAIL = "apps.users.services._send_email_safe"
PATCH_DELAY = "apps.users.services._dummy_delay"

CACHE_SETTINGS = {
    "CACHES": {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
}


@override_settings(**CACHE_SETTINGS)
class PasswordChangeTests(TestCase):

    def setUp(self):
        cache.clear()
        self.user = BaseUserFactory(password="OldPassw0rd!")

    def tearDown(self):
        cache.clear()

    @patch(PATCH_EMAIL)
    def test_happy_path_changes_password(self, mock_email):
        password_change(user=self.user, current_password="OldPassw0rd!", new_password="NewPassw0rd!")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewPassw0rd!"))

    @patch(PATCH_EMAIL)
    def test_rotates_jwt_key(self, mock_email):
        old_key = self.user.jwt_key
        password_change(user=self.user, current_password="OldPassw0rd!", new_password="NewPassw0rd!")
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.jwt_key, old_key)

    @patch(PATCH_EMAIL)
    def test_sends_notification_email(self, mock_email):
        password_change(user=self.user, current_password="OldPassw0rd!", new_password="NewPassw0rd!")
        mock_email.assert_called_once()
        args, _ = mock_email.call_args
        self.assertEqual(args[0], "password_changed_notification")

    def test_wrong_current_password_raises(self):
        with self.assertRaises(ApplicationError) as ctx:
            password_change(user=self.user, current_password="WrongOld!", new_password="NewPassw0rd!")
        self.assertIn("actuel", str(ctx.exception))

    def test_same_password_raises(self):
        with self.assertRaises(ApplicationError) as ctx:
            password_change(user=self.user, current_password="OldPassw0rd!", new_password="OldPassw0rd!")
        self.assertIn("différent", str(ctx.exception))

    def test_weak_new_password_raises(self):
        with self.assertRaises(ApplicationError):
            password_change(user=self.user, current_password="OldPassw0rd!", new_password="123")


@override_settings(**CACHE_SETTINGS)
class PasswordResetRequestTests(TestCase):

    def setUp(self):
        cache.clear()
        self.user = BaseUserFactory(email="user@example.com")

    def tearDown(self):
        cache.clear()

    @patch(PATCH_EMAIL)
    def test_sends_reset_email_for_existing_user(self, mock_email):
        password_reset_request(email="user@example.com", ip="1.2.3.4")
        mock_email.assert_called_once()
        args, _ = mock_email.call_args
        self.assertEqual(args[0], "password_reset")

    @patch(PATCH_DELAY)
    @patch(PATCH_EMAIL)
    def test_no_email_for_unknown_user_anti_enum(self, mock_email, mock_delay):
        password_reset_request(email="unknown@example.com", ip="1.2.3.4")
        mock_email.assert_not_called()
        mock_delay.assert_called_once()  # Délai factice appelé

    @patch(PATCH_EMAIL)
    def test_no_email_for_inactive_user(self, mock_email):
        InactiveUserFactory(email="inactive@example.com")
        with patch(PATCH_DELAY):
            password_reset_request(email="inactive@example.com", ip="1.2.3.4")
        mock_email.assert_not_called()

    @patch(PATCH_EMAIL)
    def test_reset_token_stored(self, mock_email):
        with patch("apps.users.services.generate_url_token", return_value="mytoken") as mock_gen:
            password_reset_request(email="user@example.com", ip="1.2.3.4")
        result = token_get("pwd_reset", "mytoken")
        self.assertIsNotNone(result)
        self.assertEqual(result["user_id"], self.user.id)

    @patch(PATCH_EMAIL)
    def test_rate_limit_blocks_after_limit(self, mock_email):
        ip = "9.9.9.9"
        # Les 5 premiers passent (limite = 5)
        for _ in range(5):
            with patch(PATCH_DELAY):
                password_reset_request(email="unknown@example.com", ip=ip)

        with self.assertRaises(OtpRateLimitError):
            password_reset_request(email="user@example.com", ip=ip)

    @patch(PATCH_EMAIL)
    def test_email_case_insensitive(self, mock_email):
        password_reset_request(email="USER@EXAMPLE.COM", ip="1.2.3.4")
        mock_email.assert_called_once()


@override_settings(**CACHE_SETTINGS)
class PasswordResetConfirmTests(TestCase):

    def setUp(self):
        cache.clear()
        self.user = BaseUserFactory(password="OldPassw0rd!")
        self.token = generate_url_token()
        token_store("pwd_reset", self.token, {"user_id": self.user.id}, ttl=RESET_TOKEN_TTL)

    def tearDown(self):
        cache.clear()

    def test_sets_new_password(self):
        password_reset_confirm(token=self.token, new_password="NewPassw0rd!")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewPassw0rd!"))

    def test_rotates_jwt_key(self):
        old_key = self.user.jwt_key
        password_reset_confirm(token=self.token, new_password="NewPassw0rd!")
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.jwt_key, old_key)

    def test_invalid_token_raises(self):
        with self.assertRaises(TokenInvalidError):
            password_reset_confirm(token="invalid_token", new_password="NewPassw0rd!")

    def test_token_consumed_anti_replay(self):
        password_reset_confirm(token=self.token, new_password="NewPassw0rd!")
        with self.assertRaises(TokenInvalidError):
            password_reset_confirm(token=self.token, new_password="AnotherPassw0rd!")

    def test_weak_new_password_raises(self):
        with self.assertRaises(ApplicationError):
            password_reset_confirm(token=self.token, new_password="123")

    def test_unknown_user_id_in_token_raises(self):
        bad_token = generate_url_token()
        token_store("pwd_reset", bad_token, {"user_id": 999999}, ttl=RESET_TOKEN_TTL)
        with self.assertRaises(TokenInvalidError):
            password_reset_confirm(token=bad_token, new_password="NewPassw0rd!")

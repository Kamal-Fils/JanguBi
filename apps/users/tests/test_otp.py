"""
Tests unitaires pour apps/users/otp.py

Stratégie : le cache Redis est mocké via django.test.override_settings
pour utiliser LocMemCache (pas de dépendance Redis réelle en tests unitaires).
"""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.core.exceptions import OtpExpiredError, OtpInvalidError, OtpLockedError, OtpRateLimitError
from apps.users.otp import (
    MAX_OTP_ATTEMPTS,
    generate_otp_code,
    generate_url_token,
    otp_store,
    otp_verify,
    rate_limit_check,
    token_consume,
    token_get,
    token_store,
)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)
class GenerateOtpCodeTests(TestCase):
    def test_returns_six_digits(self):
        code = generate_otp_code()
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())

    def test_zero_padded(self):
        # Simule un code < 100000 → doit être zero-padded
        with patch("apps.users.otp.secrets.randbelow", return_value=42):
            code = generate_otp_code()
        self.assertEqual(code, "000042")

    def test_uniqueness(self):
        codes = {generate_otp_code() for _ in range(50)}
        # Sur 50 appels au CSPRNG, on ne doit pratiquement jamais avoir 50 identiques
        self.assertGreater(len(codes), 1)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)
class GenerateUrlTokenTests(TestCase):
    def test_not_empty(self):
        token = generate_url_token()
        self.assertTrue(len(token) > 0)

    def test_url_safe_chars(self):
        token = generate_url_token()
        # token_urlsafe utilise base64url → pas de +, /
        self.assertNotIn("+", token)
        self.assertNotIn("/", token)

    def test_uniqueness(self):
        tokens = {generate_url_token() for _ in range(10)}
        self.assertEqual(len(tokens), 10)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)
class OtpStoreAndVerifyTests(TestCase):

    def setUp(self):
        cache.clear()
        self.user_id = 1
        self.action = "email_change"

    def tearDown(self):
        cache.clear()

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_valid_code_returns_exchange_token(self):
        code = "123456"
        otp_store(self.user_id, self.action, code)
        exchange = otp_verify(self.user_id, self.action, code)
        self.assertIsNotNone(exchange)
        self.assertIsInstance(exchange, str)
        self.assertGreater(len(exchange), 0)

    def test_code_with_spaces_is_accepted(self):
        code = "123456"
        otp_store(self.user_id, self.action, code)
        exchange = otp_verify(self.user_id, self.action, "123 456")
        self.assertIsNotNone(exchange)

    def test_code_with_dash_is_accepted(self):
        code = "654321"
        otp_store(self.user_id, self.action, code)
        exchange = otp_verify(self.user_id, self.action, "654-321")
        self.assertIsNotNone(exchange)

    # ------------------------------------------------------------------
    # Anti-replay : le code ne peut être utilisé qu'une fois
    # ------------------------------------------------------------------

    def test_code_consumed_after_success(self):
        code = "111111"
        otp_store(self.user_id, self.action, code)
        otp_verify(self.user_id, self.action, code)

        # Deuxième usage → OTP supprimé → expiré
        with self.assertRaises(OtpExpiredError):
            otp_verify(self.user_id, self.action, code)

    # ------------------------------------------------------------------
    # Codes invalides
    # ------------------------------------------------------------------

    def test_wrong_code_raises_invalid(self):
        otp_store(self.user_id, self.action, "123456")
        with self.assertRaises(OtpInvalidError):
            otp_verify(self.user_id, self.action, "000000")

    def test_expired_otp_raises_expired(self):
        # Pas d'OTP en cache → expire / inexistant
        with self.assertRaises(OtpExpiredError):
            otp_verify(self.user_id, self.action, "123456")

    # ------------------------------------------------------------------
    # Machine à états : LOCKED après MAX_OTP_ATTEMPTS
    # ------------------------------------------------------------------

    def test_locked_after_max_attempts(self):
        otp_store(self.user_id, self.action, "999999")
        for _ in range(MAX_OTP_ATTEMPTS - 1):
            try:
                otp_verify(self.user_id, self.action, "000000")
            except OtpInvalidError:
                pass

        # Dernière tentative → OtpLockedError
        with self.assertRaises(OtpLockedError):
            otp_verify(self.user_id, self.action, "000000")

    def test_locked_otp_destroyed(self):
        otp_store(self.user_id, self.action, "999999")
        for _ in range(MAX_OTP_ATTEMPTS):
            try:
                otp_verify(self.user_id, self.action, "000000")
            except (OtpInvalidError, OtpLockedError):
                pass

        # Même le bon code ne fonctionne plus
        with self.assertRaises((OtpExpiredError, OtpLockedError)):
            otp_verify(self.user_id, self.action, "999999")

    # ------------------------------------------------------------------
    # Isolation entre utilisateurs
    # ------------------------------------------------------------------

    def test_otp_is_user_scoped(self):
        code = "123456"
        otp_store(user_id=1, action=self.action, code=code)
        # L'utilisateur 2 ne doit pas accéder à l'OTP de l'utilisateur 1
        with self.assertRaises(OtpExpiredError):
            otp_verify(user_id=2, action=self.action, input_code=code)

    # ------------------------------------------------------------------
    # Isolation entre actions
    # ------------------------------------------------------------------

    def test_otp_is_action_scoped(self):
        code = "123456"
        otp_store(user_id=1, action="email_change", code=code)
        with self.assertRaises(OtpExpiredError):
            otp_verify(user_id=1, action="other_action", input_code=code)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)
class TokenTests(TestCase):

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_store_and_get(self):
        token = generate_url_token()
        payload = {"user_id": 42}
        token_store("pwd_reset", token, payload, ttl=300)
        result = token_get("pwd_reset", token)
        self.assertEqual(result, payload)

    def test_get_unknown_token_returns_none(self):
        result = token_get("pwd_reset", "bad_token")
        self.assertIsNone(result)

    def test_consume_returns_payload_and_deletes(self):
        token = generate_url_token()
        payload = {"user_id": 7}
        token_store("email_verify", token, payload, ttl=300)

        # Premier consume → OK
        result = token_consume("email_verify", token)
        self.assertEqual(result, payload)

        # Deuxième consume → None (anti-replay)
        result2 = token_consume("email_verify", token)
        self.assertIsNone(result2)

    def test_token_is_action_scoped(self):
        token = generate_url_token()
        payload = {"user_id": 1}
        token_store("pwd_reset", token, payload, ttl=300)

        # Même token, action différente → None
        result = token_get("email_verify", token)
        self.assertIsNone(result)

    def test_sha256_keyed_not_cleartext(self):
        """Le token en clair ne doit JAMAIS être stocké en Redis."""
        token = "mysecrettoken"
        token_store("pwd_reset", token, {"user_id": 1}, ttl=300)

        # La clé Redis contient le hash, pas le token
        raw = cache.get(f"token:pwd_reset:{token}")
        self.assertIsNone(raw, "Le token en clair est stocké en Redis — FAILLE SÉCURITÉ")


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)
class RateLimitTests(TestCase):

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_under_limit_passes(self):
        ip = "1.2.3.4"
        for _ in range(5):
            rate_limit_check("pwd_reset", ip, limit=5, window=3600)
        # Pas d'exception → OK

    def test_over_limit_raises(self):
        ip = "5.6.7.8"
        for _ in range(5):
            try:
                rate_limit_check("pwd_reset", ip, limit=5, window=3600)
            except OtpRateLimitError:
                pass

        with self.assertRaises(OtpRateLimitError):
            rate_limit_check("pwd_reset", ip, limit=5, window=3600)

    def test_no_ip_always_passes(self):
        # IP None → pas de rate limit (ex: requête interne)
        for _ in range(100):
            rate_limit_check("pwd_reset", None, limit=5, window=3600)
        # Pas d'exception → OK

    def test_different_ips_are_independent(self):
        # Bloquer une IP ne doit pas bloquer une autre
        for _ in range(10):
            try:
                rate_limit_check("pwd_reset", "1.1.1.1", limit=5, window=3600)
            except OtpRateLimitError:
                pass

        rate_limit_check("pwd_reset", "2.2.2.2", limit=5, window=3600)
        # Pas d'exception → OK

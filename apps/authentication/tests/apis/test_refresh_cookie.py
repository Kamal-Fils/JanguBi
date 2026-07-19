"""
Tests d'intégration — transport du refresh token par cookie HttpOnly.

Le refresh token vit 7 jours. Renvoyé dans le corps et stocké en `localStorage`,
il était lisible par tout script de la page : une XSS donnait une prise de compte
d'une semaine. Ces tests verrouillent le contrat qui l'en sort :

  - mode web (`X-Auth-Transport: cookie`) → cookie posé ET jeton ABSENT du corps
  - mode mobile (sans en-tête)            → comportement historique inchangé
  - refresh par cookie / par corps (repli)
  - rotation : le nouveau jeton remplace le cookie
  - logout / logout-all : cookie effacé
  - refresh sans cookie ni corps → échec propre (401)
"""

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.authentication.cookies import AUTH_TRANSPORT_COOKIE
from apps.users.tests.factories import BaseUserFactory

CACHE_SETTINGS = {
    "CACHES": {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
}

COOKIE_NAME = settings.JWT_REFRESH_COOKIE_NAME

# APIClient traduit les kwargs en en-têtes META.
COOKIE_MODE = {"HTTP_X_AUTH_TRANSPORT": AUTH_TRANSPORT_COOKIE}

PASSWORD = "TestPassw0rd!"


@override_settings(**CACHE_SETTINGS)
class RefreshCookieTransportTests(TestCase):
    def setUp(self):
        # LoginRateThrottle compte 10 tentatives/minute par IP dans le cache, et
        # LocMemCache survit d'un test à l'autre : sans ce reset, les logins de
        # cette classe épuisent le quota et font échouer les tests suivants en 429.
        cache.clear()
        self.client = APIClient()
        self.login_url = reverse("api:authentication:jwt-login")
        self.refresh_url = reverse("api:authentication:jwt-refresh")
        self.logout_url = reverse("api:authentication:jwt-logout")
        self.logout_all_url = reverse("api:authentication:jwt-logout-all")
        self.user = BaseUserFactory(email="cookie@example.com", password=PASSWORD)

    # -- helpers ----------------------------------------------------------

    def _login(self, **extra):
        return self.client.post(
            self.login_url,
            {"email": "cookie@example.com", "password": PASSWORD},
            **extra,
        )

    # -- login ------------------------------------------------------------

    def test_login_in_cookie_mode_sets_cookie_and_omits_token_from_body(self):
        # Act
        response = self._login(**COOKIE_MODE)

        # Assert — le jeton est dans le cookie…
        self.assertEqual(200, response.status_code)
        self.assertIn(COOKIE_NAME, response.cookies)
        self.assertTrue(response.cookies[COOKIE_NAME].value)

        # …et SURTOUT il a disparu du corps : le laisser aussi dans la réponse
        # annulerait le bénéfice (une XSS le lirait au moment de la connexion).
        self.assertNotIn("refresh", response.data)
        self.assertIn("access", response.data)

    def test_login_cookie_has_hardening_attributes(self):
        response = self._login(**COOKIE_MODE)
        cookie = response.cookies[COOKIE_NAME]

        self.assertTrue(cookie["httponly"], "le cookie doit être illisible depuis JS")
        self.assertEqual(settings.JWT_REFRESH_COOKIE_PATH, cookie["path"])
        self.assertEqual(settings.JWT_REFRESH_COOKIE_SAMESITE, cookie["samesite"])
        # Portée restreinte : il ne doit pas partir sur chaque appel d'API.
        self.assertNotEqual("/", cookie["path"])

    def test_login_without_header_keeps_token_in_body(self):
        # Non-régression client mobile : sans l'en-tête, rien ne change.
        response = self._login()

        self.assertEqual(200, response.status_code)
        self.assertIn("refresh", response.data)
        self.assertTrue(response.data["refresh"])
        self.assertNotIn(COOKIE_NAME, response.cookies)

    # -- refresh ----------------------------------------------------------

    def test_refresh_reads_the_cookie(self):
        # Arrange — le client conserve le cookie entre deux appels.
        self._login(**COOKIE_MODE)

        # Act — aucun corps : le jeton ne peut venir que du cookie.
        response = self.client.post(self.refresh_url, {}, format="json", **COOKIE_MODE)

        # Assert
        self.assertEqual(200, response.status_code)
        self.assertIn("access", response.data)
        self.assertNotIn("refresh", response.data)

    def test_refresh_rotation_replaces_the_cookie(self):
        # Arrange
        login = self._login(**COOKIE_MODE)
        first_token = login.cookies[COOKIE_NAME].value

        # Act
        response = self.client.post(self.refresh_url, {}, format="json", **COOKIE_MODE)

        # Assert — ROTATE_REFRESH_TOKENS est actif : le cookie doit porter le
        # NOUVEAU jeton, sinon le navigateur renverrait un jeton blacklisté.
        self.assertIn(COOKIE_NAME, response.cookies)
        self.assertNotEqual(first_token, response.cookies[COOKIE_NAME].value)

    def test_refresh_falls_back_to_request_body(self):
        # Repli client natif : pas de cookie, jeton dans le corps.
        login = self._login()
        refresh = login.data["refresh"]

        response = APIClient().post(
            self.refresh_url, {"refresh": refresh}, format="json"
        )

        self.assertEqual(200, response.status_code)
        self.assertIn("access", response.data)
        # Sans mode cookie, la rotation reste dans le corps.
        self.assertIn("refresh", response.data)

    def test_refresh_prefers_cookie_over_body(self):
        # Arrange — cookie valide + corps porteur d'un jeton bidon.
        self._login(**COOKIE_MODE)

        # Act
        response = self.client.post(
            self.refresh_url, {"refresh": "jeton-invalide"}, format="json", **COOKIE_MODE
        )

        # Assert — le cookie prime, donc ça passe malgré le corps invalide.
        self.assertEqual(200, response.status_code)

    def test_refresh_works_with_no_request_body_at_all(self):
        # Forme EXACTE émise par le client web : le corps est vide (et non `{}`).
        # Un corps vide avec Content-Type: application/json est un classique
        # générateur de « JSON parse error » 400 — on verrouille que non.
        self._login(**COOKIE_MODE)

        response = self.client.post(
            self.refresh_url, data="", content_type="application/json", **COOKIE_MODE
        )

        self.assertEqual(200, response.status_code)
        self.assertIn("access", response.data)

    def test_logout_works_with_no_request_body_at_all(self):
        login = self._login(**COOKIE_MODE)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

        response = self.client.post(
            self.logout_url, data="", content_type="application/json", **COOKIE_MODE
        )

        self.assertEqual(204, response.status_code)

    def test_refresh_without_cookie_nor_body_fails_cleanly(self):
        # Ni cookie ni corps → 401 explicite, pas un 500.
        response = APIClient().post(self.refresh_url, {}, format="json")

        self.assertEqual(401, response.status_code)
        self.assertIn("detail", response.data)

    def test_refresh_with_invalid_cookie_is_rejected(self):
        client = APIClient()
        client.cookies[COOKIE_NAME] = "pas-un-jwt"

        response = client.post(self.refresh_url, {}, format="json", **COOKIE_MODE)

        self.assertEqual(401, response.status_code)

    # -- logout -----------------------------------------------------------

    def test_logout_reads_cookie_blacklists_and_clears_it(self):
        # Arrange
        login = self._login(**COOKIE_MODE)
        access = login.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        # Act — aucun corps : le jeton vient du cookie.
        response = self.client.post(self.logout_url, {}, format="json", **COOKIE_MODE)

        # Assert
        self.assertEqual(204, response.status_code)
        self.assertIn(COOKIE_NAME, response.cookies)
        self.assertEqual("", response.cookies[COOKIE_NAME].value)
        self.assertEqual(settings.JWT_REFRESH_COOKIE_PATH, response.cookies[COOKIE_NAME]["path"])

        # Le jeton est bien révoqué : un refresh ultérieur échoue.
        self.assertEqual(
            401,
            self.client.post(self.refresh_url, {}, format="json", **COOKIE_MODE).status_code,
        )

    def test_logout_still_accepts_the_body(self):
        # Non-régression client mobile.
        login = self._login()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

        response = client.post(
            self.logout_url, {"refresh": login.data["refresh"]}, format="json"
        )

        self.assertEqual(204, response.status_code)

    def test_logout_without_any_token_returns_400(self):
        login = self._login()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

        response = client.post(self.logout_url, {}, format="json")

        self.assertEqual(400, response.status_code)

    def test_logout_all_clears_the_cookie(self):
        login = self._login(**COOKIE_MODE)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

        response = self.client.post(self.logout_all_url, **COOKIE_MODE)

        self.assertEqual(204, response.status_code)
        self.assertIn(COOKIE_NAME, response.cookies)
        self.assertEqual("", response.cookies[COOKIE_NAME].value)

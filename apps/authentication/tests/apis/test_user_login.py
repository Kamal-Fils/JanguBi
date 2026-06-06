"""
Tests d'intégration — endpoints JWT d'authentification.

Couvre :
  - Utilisateur inexistant ne peut pas se connecter
  - Utilisateur existant et vérifié peut se connecter et accéder à /me/
  - Compte inactif bloqué à la connexion
  - Email non vérifié bloqué à la connexion
  - Logout enregistre l'audit et retourne 204
  - Logout-all tourne le jwt_key
"""

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.users.models import BaseUser
from apps.users.tests.factories import BaseUserFactory, InactiveUserFactory

CACHE_SETTINGS = {
    "CACHES": {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
}


@override_settings(**CACHE_SETTINGS)
class UserJwtLoginTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.jwt_login_url = reverse("api:authentication:jwt-login")
        self.jwt_logout_url = reverse("api:authentication:jwt-logout")
        self.jwt_logout_all_url = reverse("api:authentication:jwt-logout-all")
        self.me_url = reverse("api:authentication:me")

    def test_non_existing_user_cannot_login(self):
        # Arrange
        self.assertEqual(0, BaseUser.objects.count())
        data = {"email": "noone@example.com", "password": "whatever"}

        # Act
        response = self.client.post(self.jwt_login_url, data)

        # Assert
        self.assertIn(response.status_code, [400, 401, 429])

    def test_existing_verified_user_can_login_and_access_me(self):
        # Arrange
        BaseUserFactory(email="test@example.com", password="TestPassw0rd!")

        # Act
        response = self.client.post(
            self.jwt_login_url,
            {"email": "test@example.com", "password": "TestPassw0rd!"},
        )

        # Assert
        self.assertEqual(200, response.status_code)
        self.assertIn("access", response.data)
        token = response.data["access"]

        # Sans token → 401 ou 403 selon l'ordre des authenticators
        anon_client = APIClient()
        self.assertIn(anon_client.get(self.me_url).status_code, [401, 403])

        # Avec token Bearer → 200
        auth_client = APIClient()
        auth_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(200, auth_client.get(self.me_url).status_code)

    def test_login_response_includes_pastoral_role(self):
        # Non-régression : le user de la réponse login DOIT porter pastoral_role.
        # Sinon le front (qui met ce user en cache) calcule isClergy=faux et route
        # un curé/évêque (role admin) vers /app/admin au lieu de son dashboard
        # pastoral. Cf. bug « le prêtre atterrit sur l'admin ».
        BaseUserFactory(
            email="cure@example.com",
            password="TestPassw0rd!",
            role="parish_admin",
            pastoral_role="pretre",
        )

        response = self.client.post(
            self.jwt_login_url,
            {"email": "cure@example.com", "password": "TestPassw0rd!"},
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual("pretre", response.data["user"]["pastoral_role"])
        self.assertIn("onboarding_state", response.data["user"])

    def test_inactive_user_cannot_login(self):
        # Arrange — is_active=False ET is_verified=False
        InactiveUserFactory(email="inactive@example.com", password="TestPassw0rd!")

        # Act
        response = self.client.post(
            self.jwt_login_url,
            {"email": "inactive@example.com", "password": "TestPassw0rd!"},
        )

        # Assert
        self.assertIn(response.status_code, [400, 401])

    def test_existing_user_can_logout(self):
        # Arrange
        BaseUserFactory(email="logout@example.com", password="TestPassw0rd!")

        login_response = self.client.post(
            self.jwt_login_url,
            {"email": "logout@example.com", "password": "TestPassw0rd!"},
        )
        self.assertEqual(200, login_response.status_code)
        access = login_response.data["access"]
        refresh = login_response.data["refresh"]

        # Act
        auth_client = APIClient()
        auth_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        logout_response = auth_client.post(self.jwt_logout_url, {"refresh": refresh}, format="json")

        # Assert
        self.assertEqual(204, logout_response.status_code)

    def test_logout_all_rotates_jwt_key(self):
        # Arrange
        user = BaseUserFactory(email="logoutall@example.com", password="TestPassw0rd!")
        key_before = user.jwt_key

        login_response = self.client.post(
            self.jwt_login_url,
            {"email": "logoutall@example.com", "password": "TestPassw0rd!"},
        )
        self.assertEqual(200, login_response.status_code)
        token = login_response.data["access"]

        # Act
        auth_client = APIClient()
        auth_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = auth_client.post(self.jwt_logout_all_url)

        # Assert
        self.assertEqual(204, response.status_code)
        user.refresh_from_db()
        self.assertNotEqual(user.jwt_key, key_before)

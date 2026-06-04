"""
Chantier 6b — verrou du schéma OpenAPI.

GET /api/schema/ doit répondre 200 (et en JSON) : prérequis de la régénération du
client typé front (openapi-typescript). Verrouille contre toute régression future
(serializer / @extend_schema cassé qui ferait 500).
"""

import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_api_schema_returns_200():
    resp = APIClient().get("/api/schema/")
    assert resp.status_code == 200


@pytest.mark.django_db
def test_api_schema_json_returns_200():
    resp = APIClient().get("/api/schema/", {"format": "json"})
    assert resp.status_code == 200

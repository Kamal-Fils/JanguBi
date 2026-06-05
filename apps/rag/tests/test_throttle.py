"""BUG (CRITICAL) — l'endpoint RAG n'était pas throttlé.

`RagChatApi` déclarait `UserRateThrottle` mais aucun rate 'user' n'existait dans
REST_FRAMEWORK => `rate=None` => throttle silencieusement désactivé sur un
endpoint coûteux. Corrigé via `ScopedRateThrottle` (scope 'rag') + rate défini.
"""

from unittest.mock import AsyncMock, patch

import pytest
from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

from apps.rag.service import RAGService
from apps.users.tests.factories import BaseUserFactory


def _rf_with_rag_rate(rate: str) -> dict:
    rf = dict(settings.REST_FRAMEWORK)
    rf["DEFAULT_THROTTLE_RATES"] = {"anon": None, "user": None, "rag": rate}
    return rf


@pytest.mark.django_db
def test_rag_endpoint_is_throttled():
    cache.clear()
    client = APIClient()
    client.force_authenticate(user=BaseUserFactory())

    fake = AsyncMock(return_value={"answer": "ok", "context": "ctx", "intent": {}})

    # 2 requêtes autorisées, la 3e doit être bloquée (429).
    with override_settings(REST_FRAMEWORK=_rf_with_rag_rate("2/min")):
        with patch.object(RAGService, "process_query", fake):
            r1 = client.post("/api/v1/rag/query/", {"query": "Jésus"}, format="json")
            r2 = client.post("/api/v1/rag/query/", {"query": "Jésus"}, format="json")
            r3 = client.post("/api/v1/rag/query/", {"query": "Jésus"}, format="json")

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429  # ROUGE avant le fix (throttle inopérant => 200)
    cache.clear()

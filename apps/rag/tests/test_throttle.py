"""BUG (CRITICAL) — l'endpoint RAG n'était pas throttlé.

`RagChatApi` déclarait `UserRateThrottle` mais aucun rate 'user' n'existait dans
REST_FRAMEWORK => `rate=None` => throttle silencieusement désactivé sur un
endpoint coûteux. Corrigé via `ScopedRateThrottle` (scope 'rag') + rate défini.
"""

from unittest.mock import AsyncMock, patch

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from apps.rag.service import RAGService
from apps.rag.views import RagChatApi
from apps.users.tests.factories import BaseUserFactory


class _TwoPerMinThrottle(ScopedRateThrottle):
    """Rate fixe et déterministe pour le test (indépendant des settings DRF cachés)."""

    def get_rate(self):
        return "2/min"


@pytest.mark.django_db
def test_rag_endpoint_is_throttled():
    cache.clear()
    client = APIClient()
    client.force_authenticate(user=BaseUserFactory())

    fake = AsyncMock(return_value={"answer": "ok", "context": "ctx", "intent": {}})

    # 2 requêtes autorisées, la 3e doit être bloquée (429).
    with patch.object(RagChatApi, "throttle_classes", [_TwoPerMinThrottle]):
        with patch.object(RAGService, "process_query", fake):
            r1 = client.post("/api/v1/rag/query/", {"query": "Jésus"}, format="json")
            r2 = client.post("/api/v1/rag/query/", {"query": "Jésus"}, format="json")
            r3 = client.post("/api/v1/rag/query/", {"query": "Jésus"}, format="json")

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429  # ROUGE avant le fix (throttle inopérant => 200)
    cache.clear()


@pytest.mark.django_db
def test_rag_view_uses_scoped_throttle():
    # Garde-fou : la vue déclare bien un ScopedRateThrottle de scope 'rag'
    # (et non plus UserRateThrottle sans rate).
    assert RagChatApi.throttle_scope == "rag"
    assert ScopedRateThrottle in RagChatApi.throttle_classes

"""RAGService en mode EXTRACTIF (zéro LLM) — RAG gratuit.

Vérifie que process_query restitue les passages réels sans appeler de LLM, et
gère proprement l'absence de contexte. Le LLM (optionnel) n'est jamais sollicité
ici (RAG_GENERATION_ENABLED par défaut False)."""

from unittest.mock import AsyncMock

import pytest

from apps.rag.context_builder import ContextBuilder
from apps.rag.extractor import IntentExtractor
from apps.rag.service import RAGService


class _FakeRouter:
    def __init__(self, results):
        self._results = results

    async def route_to_engines(self, intent_data):
        return self._results


def _service(router, llm=None):
    return RAGService(
        extractor=IntentExtractor(),
        router=router,
        context_builder=ContextBuilder(),
        final_llm=llm or AsyncMock(),
    )


@pytest.mark.asyncio
async def test_extractive_answer_contains_real_passages_without_llm():
    bible_ctx = "Livre: Jean 3:16\nTexte: Car Dieu a tant aimé le monde..."
    llm = AsyncMock()
    service = _service(_FakeRouter({"bible": bible_ctx}), llm=llm)

    result = await service.process_query("Parle-moi de l'amour de Dieu")

    assert "Jean 3:16" in result["answer"]
    assert bible_ctx in result["context"]
    llm.generate_text.assert_not_awaited()  # AUCUN appel LLM en mode extractif


@pytest.mark.asyncio
async def test_empty_context_returns_graceful_message_and_no_llm():
    llm = AsyncMock()
    service = _service(_FakeRouter({}), llm=llm)  # aucun engine -> contexte vide

    result = await service.process_query("question sans réponse en base")

    assert result["context"] == ""
    assert "ne trouve" in result["answer"].lower()
    llm.generate_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_blank_query_short_circuits():
    service = _service(_FakeRouter({}))
    result = await service.process_query("   ")
    assert result["context"] == ""


@pytest.mark.django_db
@pytest.mark.usefixtures("db")
def test_rag_endpoint_returns_200_with_empty_context(settings):
    """Bout-en-bout (pipeline réel, DB vide) : 200 même si le contexte est vide.
    Valide le fix serializer (context allow_blank) — avant : 400.

    On force stub/pgvector-off pour que ce test ne charge JAMAIS de modèle ML,
    quelle que soit la config .env active (la suite tourne sous base)."""
    settings.EMBEDDING_PROVIDER = "stub"
    settings.PGVECTOR_ENABLED = False

    from rest_framework.test import APIClient

    from apps.users.tests.factories import BaseUserFactory

    client = APIClient()
    client.force_authenticate(user=BaseUserFactory())
    resp = client.post("/api/v1/rag/query/", {"query": "amour de Dieu"}, format="json")

    assert resp.status_code == 200
    assert "answer" in resp.data
    assert resp.data["context"] == ""  # DB vide -> pas de contexte, mais pas de 400

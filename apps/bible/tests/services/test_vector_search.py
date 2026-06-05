"""Recherche vectorielle cosine (BUG-audit C4).

Avant : opérateur L2 (<->) sans index ; scores NULL sur embeddings absents.
Après : cosine (<=>) via HNSW, top-k, filtrage des embeddings NULL, fusion
hybride avec le lexical et repli gracieux.
"""

from django.db import connection
from django.test import TransactionTestCase

from apps.bible.models import Book, Chapter, Testament, Verse
from apps.bible.services.embedding_service import EmbeddingService
from apps.bible.services.search_service import SearchService


def _unit_vector(i: int) -> list:
    v = [0.0] * 768
    v[i] = 1.0
    return v


class _FixedQueryProvider:
    """Provider de test : renvoie toujours le vecteur de requête fourni."""

    def __init__(self, query_vector):
        self._qv = query_vector

    def embed_texts(self, texts):
        return [self._qv for _ in texts]


class VectorSearchTests(TransactionTestCase):
    def setUp(self):
        t = Testament.objects.create(name="Ancien Testament", slug="ancien", order=1)
        b = Book.objects.create(name="Genèse", slug="genese", testament=t, order=1)
        c = Chapter.objects.create(book=b, number=1)
        self.vA = Verse.objects.create(chapter=c, number=1, text="Alpha", source_file="bible_fr", embedding=_unit_vector(0))
        self.vB = Verse.objects.create(chapter=c, number=2, text="Beta", source_file="bible_fr", embedding=_unit_vector(1))
        self.vC = Verse.objects.create(chapter=c, number=3, text="Gamma", source_file="bible_fr", embedding=_unit_vector(2))
        # un verset SANS embedding : ne doit jamais apparaître en recherche vectorielle
        self.vNull = Verse.objects.create(chapter=c, number=4, text="Delta sans vecteur", source_file="bible_fr")
        self.service = SearchService()
        self.service.pgvector_enabled = True

    def _with_query_vector(self, qv):
        self.service.embedding_service = EmbeddingService(provider=_FixedQueryProvider(qv))

    def test_vector_search_ranks_by_cosine_and_skips_null(self):
        self._with_query_vector(_unit_vector(0))  # proche de vA

        rows = self.service._vector_search("peu importe", None, None, None, 10, source_file="bible_fr")

        ids = [r["id"] for r in rows]
        assert rows[0]["id"] == self.vA.id  # cosine = 1 -> premier
        assert abs(rows[0]["score"] - 1.0) < 1e-3
        assert self.vNull.id not in ids  # embedding NULL exclu

    def test_hybrid_merges_vector_and_lexical(self):
        with connection.cursor() as cur:
            cur.execute("UPDATE bible_verse SET tsv = to_tsvector('french', text);")
        self._with_query_vector(_unit_vector(1))  # proche de vB

        # _hybrid_search renvoie la liste PLATE classée par score combiné
        # (le regroupement final, lui, ré-ordonne par position canonique).
        rows = self.service._hybrid_search("Beta", None, None, None, 10, source_file="bible_fr")

        assert rows[0]["id"] == self.vB.id  # vecteur ET lexical favorisent vB
        assert rows[0]["score"] > 0

    def test_hybrid_falls_back_to_lexical_when_no_query_vector(self):
        with connection.cursor() as cur:
            cur.execute("UPDATE bible_verse SET tsv = to_tsvector('french', text);")
        self._with_query_vector([])  # embedding de requête vide -> repli lexical

        results = self.service.search("Alpha", use_hybrid=True, source_file="bible_fr")

        all_ids = [m["verse"]["id"] for g in results for m in g["matches"]]
        assert self.vA.id in all_ids

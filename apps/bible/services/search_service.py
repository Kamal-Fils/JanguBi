import logging
from typing import Dict, List, Optional

from django.conf import settings
from django.db import connection

from apps.bible.models import Verse
from apps.bible.services.cleaning import CleaningService
from apps.bible.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class SearchService:
    """Service handling lexical and hybrid search across verses."""

    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.pgvector_enabled = getattr(settings, "PGVECTOR_ENABLED", False)
        self.ts_config = getattr(settings, "PG_TS_CONFIG", "french")

    def search(
        self, query: str, testament_slug: Optional[str] = None,
        book_slug: Optional[str] = None, chapter_number: Optional[int] = None,
        limit: int = 100, use_hybrid: bool = False, source_file: Optional[str] = None
    ) -> List[Dict]:
        """
        Main entrypoint for search.
        Routes to hybrid or lexical based on request and settings.
        Sorts results by book/chapter/verse in the grouped output.
        """
        clean_query = CleaningService.clean_text(query)
        if not clean_query:
            return []

        # Force lexical if pgvector is off
        if use_hybrid and self.pgvector_enabled:
            raw_results = self._hybrid_search(clean_query, testament_slug, book_slug, chapter_number, limit, source_file=source_file)
        else:
            raw_results = self._lexical_search(clean_query, testament_slug, book_slug, chapter_number, limit, source_file=source_file)

        return self._group_results_by_book(raw_results)

    def _lexical_search(
        self, query: str, testament_slug: Optional[str],
        book_slug: Optional[str], chapter_number: Optional[int], limit: int, source_file: Optional[str] = "bible_fr"
    ) -> List[Dict]:
        """Full-text TSV search blended with pg_trgm trigram similarity (no external API required)."""
        sql = f"""
            SELECT
                v.id, v.chapter_id, v.number as verse_number, v.text,
                c.number as chapter_number,
                b.id as book_id, b.name as book_name, b.slug as book_slug, b.order as book_order,
                t.slug as testament_slug,
                (0.6 * ts_rank(v.tsv, plainto_tsquery('{self.ts_config}', %s))
                 + 0.4 * similarity(v.text, %s)) as score
            FROM bible_verse v
            JOIN bible_chapter c ON v.chapter_id = c.id
            JOIN bible_book b ON c.book_id = b.id
            JOIN bible_testament t ON b.testament_id = t.id
            WHERE v.tsv @@ plainto_tsquery('{self.ts_config}', %s)
        """
        params = [query, query, query]

        sql, params = self._apply_filters(sql, params, testament_slug, book_slug, chapter_number, source_file)

        sql += " ORDER BY score DESC, b.order, c.number, v.number LIMIT %s"
        params.append(limit)

        results = self._execute_search_query(sql, params)

        # Fallback to pure trigram when TSV finds nothing (short query, typo, accent mismatch)
        if not results:
            return self._trigram_fallback(query, testament_slug, book_slug, chapter_number, limit, source_file)

        return results

    def _trigram_fallback(
        self, query: str, testament_slug: Optional[str],
        book_slug: Optional[str], chapter_number: Optional[int], limit: int, source_file: Optional[str] = "bible_fr"
    ) -> List[Dict]:
        """Pure pg_trgm similarity search used when TSV yields no results."""
        sql = """
            SELECT
                v.id, v.chapter_id, v.number as verse_number, v.text,
                c.number as chapter_number,
                b.id as book_id, b.name as book_name, b.slug as book_slug, b.order as book_order,
                t.slug as testament_slug,
                similarity(v.text, %s) as score
            FROM bible_verse v
            JOIN bible_chapter c ON v.chapter_id = c.id
            JOIN bible_book b ON c.book_id = b.id
            JOIN bible_testament t ON b.testament_id = t.id
            WHERE similarity(v.text, %s) > 0.15
        """
        params = [query, query]

        sql, params = self._apply_filters(sql, params, testament_slug, book_slug, chapter_number, source_file)

        sql += " ORDER BY score DESC, b.order, c.number, v.number LIMIT %s"
        params.append(limit)

        return self._execute_search_query(sql, params)

    def _hybrid_search(
        self, query: str, testament_slug: Optional[str], 
        book_slug: Optional[str], chapter_number: Optional[int], limit: int, alpha: float = 0.7, source_file: Optional[str] = "bible_fr"
    ) -> List[Dict]:
        """Combines pgvector HNSW distance with full-text search rank."""
        query_vector = self.embedding_service.compute_query_embedding(query)
        if not query_vector:
            return self._lexical_search(query, testament_slug, book_slug, chapter_number, limit, source_file=source_file)

        vector_str = "[" + ",".join(str(f) for f in query_vector) + "]"

        sql = f"""
            WITH vector_matches AS (
                SELECT 
                    v.id,
                    1.0 / (1.0 + (v.embedding <-> %s::vector)) as vector_score,
                    ts_rank(v.tsv, plainto_tsquery('{self.ts_config}', %s)) as ft_score
                FROM bible_verse v
                JOIN bible_chapter c ON v.chapter_id = c.id
                JOIN bible_book b ON c.book_id = b.id
                JOIN bible_testament t ON b.testament_id = t.id
                WHERE 1=1
        """
        
        params = [vector_str, query]
        
        sql, params = self._apply_filters(sql, params, testament_slug, book_slug, chapter_number, source_file)
            
        sql += f"""
            )
            SELECT 
                v.id, v.chapter_id, v.number as verse_number, v.text,
                c.number as chapter_number,
                b.id as book_id, b.name as book_name, b.slug as book_slug, b.order as book_order,
                t.slug as testament_slug,
                (%s * m.vector_score + (1.0 - %s) * m.ft_score) as score
            FROM vector_matches m
            JOIN bible_verse v ON m.id = v.id
            JOIN bible_chapter c ON v.chapter_id = c.id
            JOIN bible_book b ON c.book_id = b.id
            JOIN bible_testament t ON b.testament_id = t.id
            ORDER BY score DESC, b.order, c.number, v.number
            LIMIT %s
        """
        
        params.extend([alpha, alpha, limit])

        return self._execute_search_query(sql, params)

    def _apply_filters(self, sql: str, params: list, testament_slug: Optional[str], book_slug: Optional[str], chapter_number: Optional[int], source_file: Optional[str] = "bible_fr"):
        """Évite d'écrire la même logique d'ajout de paramètres WHERE pour chaque méthode de recherche."""
        if source_file:
            sql += " AND v.source_file = %s"
            params.append(source_file)
        if testament_slug:
            sql += " AND t.slug = %s"
            params.append(testament_slug)
        if book_slug:
            sql += " AND b.slug = %s"
            params.append(book_slug)
        if chapter_number:
            sql += " AND c.number = %s"
            params.append(chapter_number)
        return sql, params

    def _execute_search_query(self, sql: str, params: list) -> List[Dict]:
        """Fusionne l'exécution du curseur de DB en un seul endroit propre."""
        results = []
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            columns = [col[0] for col in cursor.description]
            for row in cursor.fetchall():
                row_dict = dict(zip(columns, row))
                
                # Handle NULL scores caused by uncomputed embeddings
                score = row_dict.get("score")
                if score is None:
                    score = 0.0
                    row_dict["score"] = score
                    
                row_dict["no_internal_source"] = score < 0.15
                results.append(row_dict)
        return results

    def _group_results_by_book(self, raw_results: List[Dict]) -> List[Dict]:
        """Groups flat SQL results into the nested structure expected by the API."""
        grouped = {}
        for row in raw_results:
            book_id = row["book_id"]
            if book_id not in grouped:
                grouped[book_id] = {
                    "book": {
                        "id": book_id,
                        "name": row["book_name"],
                        "slug": row["book_slug"],
                        "order": row["book_order"],
                        "testament": row["testament_slug"],
                        "verse_count": 0, # not needed in search output, usually omitted
                    },
                    "matches": []
                }

            grouped[book_id]["matches"].append({
                "verse": {
                    "id": row["id"],
                    "number": row["verse_number"],
                    "chapter": {"number": row["chapter_number"]},
                    "text": row["text"],
                },
                "score": round(row["score"], 4),
                "no_internal_source": row["no_internal_source"],
                "book_order": row["book_order"],
                "chapter_number": row["chapter_number"],
                "verse_number": row["verse_number"]
            })

        # Convert to list and sort by book order
        result_list = list(grouped.values())
        result_list.sort(key=lambda x: x["book"]["order"])
        
        # Sort verses within each book
        for group in result_list:
            group["matches"].sort(key=lambda x: (x["chapter_number"], x["verse_number"]))
            # Clean up sort keys
            for m in group["matches"]:
                m.pop("book_order")
                m.pop("chapter_number")
                m.pop("verse_number")

        return result_list

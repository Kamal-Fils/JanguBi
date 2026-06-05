import logging
from asgiref.sync import sync_to_async
from apps.bible.services.search_service import SearchService
from apps.rag.schemas import EntitiesSchema

logger = logging.getLogger(__name__)

class BibleEngine:
    """
    RAG Engine for retrieving Biblical context based on extracted entities.
    """

    @sync_to_async
    def search(self, entities: EntitiesSchema) -> str:
        """
        Executes a Full-Text Search on the Bible module based on the topic.
        Returns a formatted string of the context to be injected into the LLM prompt.
        """
        topic = entities.get("topic")
        if not topic:
            return ""  # rien à chercher -> ignoré par le routeur/context_builder

        try:
            # Réutilise le SearchService Bible (hybride cosine+lexical si pgvector ON).
            service = SearchService()
            grouped_results = service.search(topic, limit=5, use_hybrid=True)

            if not grouped_results:
                return ""  # aucun résultat -> ignoré (pas de faux contenu)

            context_lines = []
            for group in grouped_results:
                book_name = group["book"]["name"]
                for match in group["matches"]:
                    chapter_nb = match["verse"]["chapter"]["number"]
                    verse_nb = match["verse"]["number"]
                    text = match["verse"]["text"]
                    context_lines.append(f"Livre: {book_name} {chapter_nb}:{verse_nb}\nTexte: {text}")

            return "\n\n".join(context_lines)

        except Exception as e:
            logger.error(f"BibleEngine error: {e}", exc_info=True)
            return ""  # erreur -> ignoré (le routeur gère le repli)

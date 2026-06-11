import datetime
import logging

from asgiref.sync import sync_to_async
from django.utils import timezone

from apps.rag.schemas import EntitiesSchema
from apps.rosary.services import RosaryService

logger = logging.getLogger(__name__)

class RosaryEngine:
    """
    RAG Engine for retrieving Rosary context based on extracted entities.
    Handles semantic search via `topic` or logic retrieval via `date` (e.g., today's mysteries).
    """

    @sync_to_async
    def search(self, entities: EntitiesSchema) -> str:
        """
        Gathers Rosary context. It blends semantic retrieval and rule-based day retrieval.
        """
        topic = entities.get("topic")
        date_str = entities.get("date")

        contexts = []

        # 1. Semantic Search (if a topic is provided)
        if topic:
            try:
                # Top 3 prayers/mysteries matching text
                results = RosaryService.search_text(topic)[:3]
                if results:
                    contexts.append("=== RÉSULTATS DE RECHERCHE TEXTUELLE ===")
                    for r in results:
                        contexts.append(f"Type: {r.get_type_display()} | Contexte: {r.text[:200]}...")
            except Exception as e:
                logger.error(f"RosaryEngine FTS error: {e}")

        # 2. Daily Logic (if 'aujourd'hui', 'demain', or a specific date is inferred)
        # For simplicity, if a date string YYYY-MM-DD is provided, we parse the weekday.
        target_weekday = None
        if date_str:
            try:
                # Protection stricte contre des formats fantaisistes de Gemini
                # S'assure que la conversion peut se faire, sinon rejeta silencieusement sur 'ajourd'hui'
                if len(date_str) == 10:
                    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                    target_weekday = dt.weekday()
                else:
                    target_weekday = timezone.now().weekday()
            except (ValueError, TypeError):
                logger.warning(f"Format de date non valide reçu de Gemini: {date_str}. Utilisation de la date du jour.")
                target_weekday = timezone.now().weekday()
        elif not topic: # If no topic but intent was Rosary, assume they want today's
            target_weekday = timezone.now().weekday()

        if target_weekday is not None:
            try:
                day_data = RosaryService.get_daily_rosary(target_weekday)
                contexts.append(f"=== MYSTÈRES DU JOUR ({day_data.get_weekday_display()}) ===")
                contexts.append(f"Groupe: {day_data.group.name}")
                
                for m in day_data.group.mysteries.all():
                    contexts.append(f"- Mystère {m.order}: {m.title}")
            except Exception as e:
                logger.error(f"RosaryEngine Daily logic error: {e}")
        
        if not contexts:
            return ""  # rien -> ignoré par le routeur/context_builder

        return "\n".join(contexts)

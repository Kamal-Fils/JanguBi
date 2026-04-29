import asyncio
import logging
from typing import Dict
from apps.rag.extractor import ExtractedIntentSchema
from apps.rag.bible_engine import BibleEngine
from apps.rag.rosary_engine import RosaryEngine

logger = logging.getLogger(__name__)

class QueryRouter:
    """
    Takes the structured intent output and dispatches queries concurrently
    to the respective engines WITH TIMEOUTS.
    """

    # Temps maximal alloué à la résolution du contexte (en secondes)
    ENGINE_TIMEOUT = 15.0

    def __init__(self):
        self.bible_engine = BibleEngine()
        self.rosary_engine = RosaryEngine()

    async def _safe_execute(self, engine_name: str, coroutine) -> str:
        """Enveloppe l'exécution d'un moteur avec un délai d'attente strict et gestion de crash."""
        try:
            return await asyncio.wait_for(coroutine, timeout=self.ENGINE_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning(f"Timeout ({self.ENGINE_TIMEOUT}s) reached for {engine_name} engine.")
            return f"[{engine_name}] Le module a mis trop de temps à répondre."
        except Exception as e:
            logger.error(f"Crash in {engine_name} engine: {e}", exc_info=True)
            return f"[{engine_name}] Erreur interne lors de la recherche."

    async def route_to_engines(self, intent_data: ExtractedIntentSchema) -> Dict[str, str]:
        """
        Runs the required engines concurrently based on the 'domains' array.
        Returns a dictionary of context strings.
        """
        domains = intent_data.get("domains", [])
        entities = intent_data.get("entities", {})

        tasks = {}

        if "BIBLE" in domains:
            tasks["bible"] = self._safe_execute("Bible", self.bible_engine.search(entities))
        
        if "ROSARY" in domains:
            tasks["rosary"] = self._safe_execute("Rosaire", self.rosary_engine.search(entities))

        results = {}
        if tasks:
            keys = list(tasks.keys())
            coroutines = list(tasks.values())
            
            try:
                # gather with return_exceptions=True is still safe, though _safe_execute catches everything
                completed = await asyncio.gather(*coroutines, return_exceptions=True)
                for idx, key in enumerate(keys):
                    res = completed[idx]
                    if isinstance(res, Exception):
                        results[key] = f"Erreur critique inattendue avec le module {key}."
                    else:
                        results[key] = res
            except Exception as e:
                logger.error(f"Asyncio gather error during routing: {e}")

        return results

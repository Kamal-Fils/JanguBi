import logging
from typing import Optional, TypedDict

from django.conf import settings

from apps.rag.context_builder import ContextBuilder
from apps.rag.extractor import IntentExtractor
from apps.rag.llm_client import AsyncGeminiClient
from apps.rag.router import QueryRouter

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# 1. Extraction du prompt hors de la logique métier
# ----------------------------------------------------------------------------
RAG_SYSTEM_PROMPT_TEMPLATE = """
Tu es un assistant IA catholique précis, rigoureux et respectueux.

Ta mission est de répondre à la question de l'utilisateur UNIQUEMENT à partir du CONTEXTE fourni.

RÈGLES ABSOLUES :

1. Tu ne dois utiliser AUCUNE connaissance externe.
2. Toutes les informations doivent provenir du CONTEXTE.
3. Les versets bibliques doivent être cités EXACTEMENT tels qu'ils apparaissent dans le contexte.
4. Ne modifie pas, ne paraphrase pas et ne complète pas les versets.
5. Si une information demandée n'est pas présente dans le contexte, réponds clairement :
   "Je ne trouve pas cette information dans le contexte fourni."

RÈGLES D'EXPLICATION :

6. Tu peux EXPLIQUER et RÉSUMER les informations présentes dans le contexte afin de répondre à la question.
7. Ton explication doit être STRICTEMENT basée sur les versets présents dans le contexte.
8. N'ajoute aucune interprétation théologique personnelle ni information extérieure.
9. Si plusieurs versets parlent du même sujet, fais une synthèse courte et claire.
10. L'explication doit rester courte (3 à 5 phrases maximum).

STRUCTURE DE LA RÉPONSE :

Ta réponse doit être organisée en deux parties :

1️⃣ Réponse synthétique  
- Explique brièvement ce que disent les passages fournis.

2️⃣ Passages bibliques cités  
- Liste les versets EXACTEMENT tels qu'ils apparaissent dans le contexte.

Style attendu :
- clair
- structuré
- neutre
- factuel
- concis

CONTEXTE :
{context}
"""

# ----------------------------------------------------------------------------
# 2. Typage robuste du retour (Clean Code)
# ----------------------------------------------------------------------------
class RAGResponse(TypedDict):
    answer: str
    context: str
    intent: dict

class RAGService:
    """
    The orchestrator that runs the entire RAG pipeline from a raw user string to the final LLM response.
    """

    # 3. Injection de dépendances pour faciliter le Mocking et les tests
    def __init__(
        self, 
        extractor: Optional[IntentExtractor] = None,
        router: Optional[QueryRouter] = None,
        context_builder: Optional[ContextBuilder] = None,
        final_llm: Optional[AsyncGeminiClient] = None
    ):
        self.extractor = extractor or IntentExtractor()
        self.router = router or QueryRouter()
        self.context_builder = context_builder or ContextBuilder()

        # Le client LLM n'est créé QUE si la génération est activée (sinon extractif
        # pur : pas de client, pas de warning de clé manquante à chaque requête).
        if final_llm is not None:
            self.final_llm = final_llm
        elif self._generation_enabled():
            model_name = getattr(settings, "GEMINI_MODEL_NAME", "gemini-2.5-flash")
            self.final_llm = AsyncGeminiClient(model_name=model_name)
        else:
            self.final_llm = None

    @staticmethod
    def _generation_enabled() -> bool:
        """La génération LLM n'est active que si explicitement demandée ET une clé
        est présente. Par défaut : extractif (gratuit)."""
        return bool(getattr(settings, "RAG_GENERATION_ENABLED", False)) and bool(
            getattr(settings, "GEMINI_API_KEY", "")
        )

    @staticmethod
    def _extractive_answer(context_string: str) -> str:
        """Réponse extractive : restitue les passages réels (aucune génération,
        aucune hallucination, fidèle au texte). Idéal pour un usage catholique."""
        return (
            "Voici les passages les plus pertinents trouvés dans nos textes de "
            "référence :\n\n" + context_string
        )

    async def process_query(self, query: str) -> RAGResponse:
        """
        Pipeline RAG : Extract (règles) -> Route/Retrieve -> Build Context ->
        Réponse extractive (par défaut) ou génération LLM (optionnelle).
        """
        # 4. Validation des entrées (Sécurité)
        if not query or not query.strip():
            return RAGResponse(answer="La requête est vide.", context="", intent={})
            
        if len(query) > 1000:  # Limite de sécurité arbitraire (ex. 1000 chars utiles)
            return RAGResponse(
                answer="Votre question est trop longue, veuillez la raccourcir.",
                context="",
                intent={}
            )

        # Troncature pour des logs propres et sans risque PII massif
        logger.info(f"RAG processing query: {query[:100]}...")

        intent_data = {}
        
        # 5. Gestion native des erreurs et pannes potentielles d'API ou de BD
        try:
            # Étape 1 : Extract
            intent_data = await self.extractor.extract(query)
            # On ne logge PAS entities.topic (= requête brute, PII potentiel) :
            # seulement intent + domains.
            logger.info(
                "Extracted intent=%s domains=%s",
                intent_data.get("intent"), intent_data.get("domains"),
            )

            # Garde défensive : requête hors périmètre (l'extracteur par règles
            # route par défaut vers BIBLE, donc rarement atteint ; AVAILABILITY
            # n'est pas câblé dans les engines -> dégradé via "aucun contexte").
            if intent_data.get("intent") == "UNKNOWN" and not intent_data.get("domains"):
                return RAGResponse(
                    answer="Désolé, je suis uniquement formé pour répondre aux questions concernant la Bible et le Rosaire. Pouvez-vous reformuler votre question ?",
                    context="",
                    intent=intent_data
                )

            # Étape 2 : Route & Retrieve
            engine_results = await self.router.route_to_engines(intent_data)

            # Étape 3 : Build Context
            context_string = self.context_builder.build(engine_results)

            # Pas de contexte -> message d'absence (aucun appel LLM).
            if not context_string or not context_string.strip():
                return RAGResponse(
                    answer="Je ne trouve malheureusement pas cette information dans mes documents de référence actuels.",
                    context="",
                    intent=intent_data
                )

            # Étape 4 : Réponse.
            # Par défaut EXTRACTIF (zéro coût LLM) : on restitue les passages réels
            # récupérés. La génération LLM est OPTIONNELLE (flag + clé présents).
            if self._generation_enabled():
                system_prompt = RAG_SYSTEM_PROMPT_TEMPLATE.format(context=context_string)
                final_answer = await self.final_llm.generate_text(
                    system_prompt=system_prompt,
                    user_prompt=query,
                )
            else:
                final_answer = self._extractive_answer(context_string)

            return RAGResponse(
                answer=final_answer,
                context=context_string,
                intent=intent_data
            )
        except Exception as e:
            # Catcher toutes les erreurs de timeout/réseau pour éviter une page 500 violente
            logger.error(f"Error processing RAG pipeline for query '{query[:50]}': {e}", exc_info=True)
            return RAGResponse(
                answer="Désolé, une erreur interne empêche de traiter votre question pour le moment. Veuillez réessayer plus tard.",
                context="",
                intent=intent_data
            )

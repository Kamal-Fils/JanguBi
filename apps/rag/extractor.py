import logging
from datetime import date, timedelta

from apps.rag.schemas import ExtractedIntentSchema

logger = logging.getLogger(__name__)

# Détection de domaine par mots-clés — 100 % local, aucun coût LLM.
BIBLE_KEYWORDS = {
    "verset", "versets", "bible", "biblique", "écriture", "ecriture", "écritures",
    "évangile", "evangile", "psaume", "psaumes", "parole", "testament", "jésus",
    "jesus", "christ", "apôtre", "apotre", "épître", "epitre", "genèse", "genese",
    "exode", "matthieu", "marc", "luc", "jean", "actes", "prophète", "prophete",
    "ancien testament", "nouveau testament",
}
ROSARY_KEYWORDS = {
    "chapelet", "rosaire", "mystère", "mystere", "mystères", "mysteres", "marie",
    "vierge", "ave maria", "je vous salue", "dizaine", "joyeux", "douloureux",
    "glorieux", "lumineux", "notre père", "notre pere", "gloire au père",
}

_TODAY_WORDS = ("aujourd'hui", "aujourdhui", "ce jour", "today", "maintenant")
_TOMORROW_WORDS = ("demain", "tomorrow")
_WEEKDAYS = {
    "lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3,
    "vendredi": 4, "samedi": 5, "dimanche": 6,
}


class IntentExtractor:
    """Extraction d'intention/entités SANS LLM (règles + mots-clés).

    Conserve une interface ``async`` pour rester compatible avec le pipeline RAG.
    La détection est volontairement inclusive (favorise le rappel pour un RAG
    extractif) ; le `topic` = la requête nettoyée (la recherche sémantique gère
    le sens). Aucun appel réseau, aucun coût.
    """

    async def extract(self, query: str) -> ExtractedIntentSchema:
        q = (query or "").lower().strip()

        domains = []
        if any(k in q for k in ROSARY_KEYWORDS):
            domains.append("ROSARY")
        if any(k in q for k in BIBLE_KEYWORDS):
            domains.append("BIBLE")
        # Défaut : la Bible (corpus principal) quand rien n'est explicitement détecté.
        if not domains:
            domains = ["BIBLE"]

        intent = "MIXED" if len(domains) > 1 else domains[0]

        return {
            "intent": intent,
            "domains": domains,
            "entities": {
                "topic": (query or "").strip(),
                "date": self._extract_date(q),
                "time_after": None,
                "city": None,
                "service": None,
            },
        }

    @staticmethod
    def _extract_date(q: str):
        """Convertit une mention de date relative en YYYY-MM-DD (pour le rosaire)."""
        if any(w in q for w in _TODAY_WORDS):
            return date.today().isoformat()
        if any(w in q for w in _TOMORROW_WORDS):
            return (date.today() + timedelta(days=1)).isoformat()
        for name, weekday in _WEEKDAYS.items():
            if name in q:
                today = date.today()
                delta = (weekday - today.weekday()) % 7
                return (today + timedelta(days=delta)).isoformat()
        return None

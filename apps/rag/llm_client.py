import json
import logging

import httpx
from django.conf import settings
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# Plafond de tokens de sortie (coût/latence bornés).
MAX_OUTPUT_TOKENS = 1024


def _is_retryable(exc: Exception) -> bool:
    """Ne retenter QUE le réseau et les 5xx. Les 4xx (401/403 clé invalide,
    400 requête, 429 quota) sont déterministes : insister aggrave la charge."""
    if isinstance(exc, httpx.RequestError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


class AsyncGeminiClient:
    """Client REST asynchrone pour l'API Google Gemini (chemin OPTIONNEL ; le RAG
    est extractif par défaut). Clé transmise par header (jamais dans l'URL)."""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, model_name="gemini-2.5-flash", api_key=None):
        self.api_key = api_key or getattr(settings, "GEMINI_API_KEY", None)
        self.model_name = model_name

        if not self.api_key:
            logger.warning("GEMINI_API_KEY is not set. LLM generation calls will fail.")

    def _headers(self) -> dict:
        return {"x-goog-api-key": self.api_key or ""}

    @property
    def _url(self) -> str:
        return f"{self.BASE_URL}/{self.model_name}:generateContent"

    async def generate_structured(self, prompt: str, schema: dict) -> dict:
        """Sortie JSON structurée (conservé pour compat ; non utilisé en mode
        extractif)."""
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": schema,
                "temperature": 0.0,
                "maxOutputTokens": MAX_OUTPUT_TOKENS,
            },
        }

        @retry(
            wait=wait_exponential(multiplier=1, min=2, max=10),
            stop=stop_after_attempt(5),
            retry=retry_if_exception(_is_retryable),
            reraise=True,
        )
        async def _make_request():
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self._url, json=payload, headers=self._headers(), timeout=10.0
                )
                response.raise_for_status()
                return response.json()

        try:
            data = await _make_request()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        except httpx.HTTPError as e:
            logger.error(f"Gemini API structured generation HTTP Error: {e}")
            return {}
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            logger.error(f"Failed to parse Gemini structured output: {e}")
            return {}

    async def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        """Génération de texte libre pour la réponse RAG finale (mode LLM optionnel)."""
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": MAX_OUTPUT_TOKENS,
            },
        }

        @retry(
            wait=wait_exponential(multiplier=1, min=2, max=10),
            stop=stop_after_attempt(5),
            retry=retry_if_exception(_is_retryable),
            reraise=True,
        )
        async def _make_request():
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self._url, json=payload, headers=self._headers(), timeout=15.0
                )
                response.raise_for_status()
                return response.json()

        try:
            data = await _make_request()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except httpx.HTTPError as e:
            logger.error(f"Gemini API text generation HTTP Error: {e}")
            return "Je suis désolé, je n'ai pas pu générer une réponse en raison d'une erreur de connexion."
        except (KeyError, IndexError) as e:
            logger.error(f"Failed to parse Gemini text output: {e}")
            return "Je suis désolé, je n'ai pas pu formater la réponse."

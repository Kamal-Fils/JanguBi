"""
Utilitaires OTP / Token pour les flux d'authentification sensibles.

Architecture (conforme au document Flux_OTP_pour_Changement_de_Compte.md) :
- Stockage Redis (Hot Data éphémère, TTL natif, opérations atomiques)
- CSPRNG exclusivement (module `secrets`) — jamais `random`
- Codes courts (6 chiffres) : HMAC-SHA256 avec SECRET_KEY comme pepper
- Tokens longs (URL) : SHA-256 du token en clair
- Comparaison à temps constant : hmac.compare_digest() — anti Timing Attack
- Machine à états : ISSUED → VERIFIED/LOCKED/EXPIRED

Clés Redis utilisées :
  otp:{action}:{user_id}            → HMAC(code),   TTL 10 min
  attempts:otp:{user_id}:{action}   → int,           TTL 10 min
  exchange:{action}:{user_id}       → token opaque,  TTL  5 min
  token:{action}:{sha256(token)}    → payload dict,  TTL variable
"""

import hashlib
import hmac
import secrets
import uuid
from typing import Any

from django.conf import settings
from django.core.cache import cache

from apps.core.exceptions import OtpExpiredError, OtpInvalidError, OtpLockedError

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

OTP_TTL = 600          # 10 min — NIST SP 800-63B
RESET_TOKEN_TTL = 1200  # 20 min — NIST SP 800-63B (magic link)
VERIFY_TOKEN_TTL = 86400  # 24h  — activation de compte
REVERT_TOKEN_TTL = 604800  # 7 jours — réversion changement email
EXCHANGE_TOKEN_TTL = 300   # 5 min  — preuve OTP vérifié
MAX_OTP_ATTEMPTS = 3


# ---------------------------------------------------------------------------
# Génération (CSPRNG — module secrets uniquement)
# ---------------------------------------------------------------------------

def generate_otp_code() -> str:
    """Code numérique 6 chiffres via CSPRNG. Entropie ~20 bits → protégé par rate limit."""
    return str(secrets.randbelow(1_000_000)).zfill(6)


def generate_url_token() -> str:
    """Token URL 32 bytes CSPRNG. Entropie 256 bits → intrinsèquement sûr."""
    return secrets.token_urlsafe(32)


# ---------------------------------------------------------------------------
# Hachage
# ---------------------------------------------------------------------------

def _hmac_hash(value: str) -> str:
    """
    HMAC-SHA256 avec SECRET_KEY comme pepper.
    Utilisé pour les codes courts (6 chiffres) : protège contre les
    rainbow tables en cas de dump Redis.
    """
    return hmac.new(
        settings.SECRET_KEY.encode(),
        value.encode(),
        hashlib.sha256,
    ).hexdigest()


def _sha256(value: str) -> str:
    """SHA-256 pour les tokens longs (haute entropie intrinsèque)."""
    return hashlib.sha256(value.encode()).hexdigest()


# ---------------------------------------------------------------------------
# OTP courts (6 chiffres) — flux email change
# ---------------------------------------------------------------------------

def otp_store(user_id: int | str | uuid.UUID, action: str, code: str, ttl: int = OTP_TTL) -> None:
    """Stocke HMAC(code) + initialise le compteur de tentatives."""
    otp_key = f"otp:{action}:{user_id}"
    attempts_key = f"attempts:otp:{user_id}:{action}"
    cache.set(otp_key, _hmac_hash(code), timeout=ttl)
    cache.set(attempts_key, 0, timeout=ttl)


def otp_verify(user_id: int | str | uuid.UUID, action: str, input_code: str) -> str:
    """
    Vérifie un code OTP et retourne un exchange token si valide.

    Sécurités implémentées :
    - Nettoyage UX (espaces / tirets)
    - Rate limit : max 3 tentatives → lock + destruction immédiate de l'OTP
    - Comparaison à temps constant (anti Timing Attack)
    - Suppression atomique après succès (anti Replay Attack)

    Returns:
        exchange_token (str) — preuve de vérification, TTL 5 min

    Raises:
        OtpLockedError   — 3 tentatives atteintes
        OtpExpiredError  — OTP expiré ou inexistant
        OtpInvalidError  — code incorrect
    """
    # Nettoyage UX : l'utilisateur peut avoir tapé "123 456" ou "123-456"
    input_code = input_code.replace(" ", "").replace("-", "")

    otp_key = f"otp:{action}:{user_id}"
    attempts_key = f"attempts:otp:{user_id}:{action}"

    # 1. Vérification du rate limit avant tout
    attempts = cache.get(attempts_key, 0)
    if attempts >= MAX_OTP_ATTEMPTS:
        cache.delete(otp_key)
        raise OtpLockedError(
            "Trop de tentatives incorrectes. Veuillez redemander un nouveau code."
        )

    # 2. Récupération du hash stocké (None = expiré ou jamais existé)
    stored_hash = cache.get(otp_key)
    if stored_hash is None:
        raise OtpExpiredError("Code expiré ou invalide.")

    # 3. Comparaison à temps constant — anti Timing Attack (OWASP)
    input_hash = _hmac_hash(input_code)
    if not hmac.compare_digest(stored_hash, input_hash):
        # Incrément atomique du compteur (préserve le TTL en Redis)
        new_attempts = cache.get_or_set(attempts_key, 0, timeout=OTP_TTL)
        new_attempts = cache.incr(attempts_key)
        if new_attempts >= MAX_OTP_ATTEMPTS:
            # Destruction immédiate après verrouillage
            cache.delete_many([otp_key, attempts_key])
            raise OtpLockedError(
                "Trop de tentatives incorrectes. Veuillez redemander un nouveau code."
            )
        raise OtpInvalidError("Code incorrect ou expiré.")

    # 4. Succès : nettoyage atomique (anti Replay Attack)
    cache.delete_many([otp_key, attempts_key])

    # 5. Émission d'un exchange token (preuve que l'OTP a été validé)
    exchange_token = secrets.token_urlsafe(16)
    cache.set(f"exchange:{action}:{user_id}", exchange_token, timeout=EXCHANGE_TOKEN_TTL)

    return exchange_token


def otp_exchange_token_verify(user_id: int, action: str, token: str) -> bool:
    """Vérifie que l'exchange token est valide (TTL 5 min)."""
    stored = cache.get(f"exchange:{action}:{user_id}")
    if not stored:
        return False
    return hmac.compare_digest(stored, token)


def otp_exchange_token_consume(user_id: int, action: str) -> None:
    """Consomme (supprime) l'exchange token après usage."""
    cache.delete(f"exchange:{action}:{user_id}")


# ---------------------------------------------------------------------------
# Tokens URL longs — flux activation email + password reset + email revert
# ---------------------------------------------------------------------------

def token_store(action: str, token: str, payload: dict[str, Any], ttl: int) -> None:
    """Stocke SHA-256(token) → payload dans Redis. Jamais le token en clair."""
    key = f"token:{action}:{_sha256(token)}"
    cache.set(key, payload, timeout=ttl)


def token_get(action: str, token: str) -> dict[str, Any] | None:
    """Récupère le payload associé au token (None si expiré / invalide)."""
    key = f"token:{action}:{_sha256(token)}"
    return cache.get(key)


def token_consume(action: str, token: str) -> dict[str, Any] | None:
    """Récupère ET supprime atomiquement (anti Replay Attack)."""
    key = f"token:{action}:{_sha256(token)}"
    payload = cache.get(key)
    if payload is not None:
        cache.delete(key)
    return payload


# ---------------------------------------------------------------------------
# Rate limiting par IP (couche 1)
# ---------------------------------------------------------------------------

def rate_limit_check(action: str, ip: str | None, limit: int = 5, window: int = 3600) -> None:
    """
    Vérifie le rate limit pour une action depuis une IP.
    Basé sur user_id/email en priorité (protection botnets),
    IP en couche complémentaire.

    Raises:
        OtpRateLimitError si limite atteinte.
    """
    from apps.core.exceptions import OtpRateLimitError

    if not ip:
        return

    key = f"ratelimit:{action}:{ip}"

    # add() ne crée la clé que si elle n'existe pas (idempotent)
    if not cache.add(key, 1, timeout=window):
        count = cache.incr(key)
        if count > limit:
            raise OtpRateLimitError(
                "Trop de tentatives depuis votre adresse. Réessayez dans une heure."
            )

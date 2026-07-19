"""
Transport du refresh token par cookie HttpOnly.

POURQUOI
--------
Le refresh token vit 7 jours. Tant qu'il était renvoyé dans le corps de réponse
et stocké côté client dans `localStorage`, tout script exécuté sur la page
pouvait le lire : une seule faille XSS suffisait à voler une session d'une
semaine — bien au-delà de la session en cours. Dans un cookie `HttpOnly`,
JavaScript ne peut plus y accéder du tout.

POURQUOI UN CHOIX EXPLICITE DU CLIENT
-------------------------------------
Une application mobile React Native est prévue (le modèle `PushDevice` existe
déjà dans apps/messaging/models.py). Un client natif ne gère pas les cookies
comme un navigateur : supprimer purement et simplement le jeton du corps de
réponse casserait ce futur client.

Le transport est donc choisi par le CLIENT, via l'en-tête `X-Auth-Transport`.
Un en-tête plutôt qu'un champ de requête, pour trois raisons :

1. `refresh` et `logout` peuvent n'avoir AUCUN corps en mode cookie (le jeton
   vient du cookie) — un champ de corps obligerait à envoyer un corps vide
   artificiel juste pour porter le drapeau.
2. Le même mécanisme couvre uniformément les quatre endpoints (login, refresh,
   logout, logout-all) sans toucher à quatre sérialiseurs.
3. Le contrat OpenAPI reste propre : le frontend génère ses types de corps de
   requête depuis le schéma (cf. JanguBiUI/src/types/api.ts). Un drapeau de
   transport n'est pas une donnée métier et n'a rien à faire dans ces types.

Sans l'en-tête, le comportement historique est strictement inchangé.
"""

from __future__ import annotations

from django.conf import settings
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_simplejwt.settings import api_settings as jwt_settings

# Valeur attendue de l'en-tête pour activer le mode cookie.
AUTH_TRANSPORT_HEADER = "X-Auth-Transport"
AUTH_TRANSPORT_COOKIE = "cookie"

# Nom de la clé META correspondante (Django préfixe et normalise les en-têtes).
_AUTH_TRANSPORT_META = "HTTP_X_AUTH_TRANSPORT"


def wants_cookie_transport(request: Request) -> bool:
    """Le client demande-t-il le transport du refresh token par cookie ?"""
    header = request.META.get(_AUTH_TRANSPORT_META, "")
    return header.strip().lower() == AUTH_TRANSPORT_COOKIE


def get_refresh_cookie(request: Request) -> str | None:
    """Retourne le refresh token porté par le cookie, s'il existe."""
    value = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
    return value or None


def read_refresh_token(request: Request) -> tuple[str | None, bool]:
    """
    Lit le refresh token, **cookie en priorité**, repli sur le corps de requête.

    Le cookie prime : c'est le canal du client web, et c'est lui qui doit être
    remplacé en cas de rotation. Le corps reste accepté pour les clients natifs
    (et pour tout appel programmatique existant).

    Retourne `(token, provenance_cookie)`.
    """
    cookie_token = get_refresh_cookie(request)
    if cookie_token:
        return cookie_token, True

    body = request.data if isinstance(request.data, dict) else {}
    body_token = body.get("refresh")
    if isinstance(body_token, str) and body_token:
        return body_token, False

    return None, False


def set_refresh_cookie(response: Response, token: str) -> Response:
    """
    Pose le refresh token dans un cookie HttpOnly.

    `max_age` suit exactement la durée de vie du jeton : un cookie qui survivrait
    à son jeton ne produirait que des refresh en échec.
    """
    # Source de vérité SimpleJWT plutôt que settings.SIMPLE_JWT["…"] : c'est elle
    # qui fait foi à l'émission du jeton, y compris sous @override_settings.
    lifetime = jwt_settings.REFRESH_TOKEN_LIFETIME

    response.set_cookie(
        key=settings.JWT_REFRESH_COOKIE_NAME,
        value=token,
        max_age=int(lifetime.total_seconds()),
        # Inaccessible à JavaScript — c'est tout l'intérêt du changement.
        httponly=True,
        # HTTPS uniquement en production (cf. config/django/production.py).
        secure=settings.JWT_REFRESH_COOKIE_SECURE,
        # Restreint aux seules routes qui en ont besoin : le cookie ne part pas
        # sur les appels d'API ordinaires.
        path=settings.JWT_REFRESH_COOKIE_PATH,
        # `Lax` bloque l'envoi sur une requête POST cross-site : un site tiers ne
        # peut donc pas déclencher un refresh ou un logout dans le dos de
        # l'utilisateur. Cf. config/settings/jwt.py pour la contrainte si le
        # front change de domaine enregistrable.
        samesite=settings.JWT_REFRESH_COOKIE_SAMESITE,
    )
    return response


def delete_refresh_cookie(response: Response) -> Response:
    """
    Efface le cookie de refresh.

    `path` et `samesite` DOIVENT correspondre à ceux utilisés à la pose : un
    navigateur n'efface un cookie que si l'attribut Path coïncide, sinon le
    cookie survit silencieusement à la déconnexion.
    """
    response.delete_cookie(
        key=settings.JWT_REFRESH_COOKIE_NAME,
        path=settings.JWT_REFRESH_COOKIE_PATH,
        samesite=settings.JWT_REFRESH_COOKIE_SAMESITE,
    )
    return response

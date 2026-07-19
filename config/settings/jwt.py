"""
Configuration JWT — djangorestframework-simplejwt (seule lib JWT réellement utilisée).

Historique : l'ancien bloc JWT_AUTH ciblait rest_framework_jwt (styria), lib absente
d'INSTALLED_APPS — SimpleJWT ne lit pas ce namespace. Conséquence : sans bloc
SIMPLE_JWT, l'access token durait 5 minutes (défaut SimpleJWT), pas les « 7 jours »
que laissait croire JWT_EXPIRATION_DELTA_SECONDS.
"""

import datetime

from config.env import env

JWT_ACCESS_TOKEN_LIFETIME_MINUTES = env.int("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", default=30)
JWT_REFRESH_TOKEN_LIFETIME_DAYS = env.int("JWT_REFRESH_TOKEN_LIFETIME_DAYS", default=7)

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": datetime.timedelta(minutes=JWT_ACCESS_TOKEN_LIFETIME_MINUTES),
    "REFRESH_TOKEN_LIFETIME": datetime.timedelta(days=JWT_REFRESH_TOKEN_LIFETIME_DAYS),
    # Chaque refresh émet un nouveau couple access+refresh ; l'ancien refresh est
    # blacklisté (app rest_framework_simplejwt.token_blacklist déjà installée).
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "UPDATE_LAST_LOGIN": False,
}

# ---------------------------------------------------------------------------
# Transport du refresh token par cookie HttpOnly (clients navigateur)
# ---------------------------------------------------------------------------
#
# Le refresh token vit 7 jours. Tant qu'il transitait par le corps de réponse et
# dormait dans localStorage, n'importe quel script exécuté sur la page pouvait le
# lire : une seule faille XSS donnait une prise de compte d'une semaine, bien
# au-delà de la session en cours. En cookie HttpOnly, JavaScript ne peut plus le
# lire du tout.
#
# Le transport est choisi PAR LE CLIENT via l'en-tête `X-Auth-Transport: cookie`
# (cf. apps/authentication/cookies.py). Sans cet en-tête, le comportement
# historique est conservé — indispensable pour le futur client React Native, qui
# ne gère pas les cookies comme un navigateur et a besoin du jeton dans le corps.
JWT_REFRESH_COOKIE_NAME = env.str("JWT_REFRESH_COOKIE_NAME", default="jb_refresh")

# Portée du cookie restreinte aux SEULES routes qui en ont besoin (login pose,
# refresh consomme, logout révoque). Inutile — et contraire au moindre privilège —
# de l'envoyer sur chaque appel d'API : moins il circule, moins il est exposé
# (logs de proxy, en-têtes trop verbeux, requêtes non liées à l'auth).
# Doit rester cohérent avec le montage des URLs (config/urls.py + apps/api/urls.py
# + apps/authentication/urls.py) : /api/ + v1/ + auth/ + jwt/<action>/.
JWT_REFRESH_COOKIE_PATH = env.str("JWT_REFRESH_COOKIE_PATH", default="/api/v1/auth/jwt/")

# `Lax` suffit tant que le front et l'API partagent le même domaine enregistrable
# (prod : guiss.kamalfils.app ↔ api-guiss.kamalfils.app ; dev : localhost:3000 ↔
# localhost:8001). Les requêtes sont alors *same-site* et le cookie part bien.
#
# ⚠️ CONTRAINTE DE DÉPLOIEMENT — À LIRE AVANT DE CHANGER DE DOMAINE DE FRONT.
# Si le front est un jour servi depuis un domaine DIFFÉRENT de l'API (une preview
# Vercel, par exemple : des origines *.vercel.app traînent dans .env.prod.example),
# les appels deviennent *cross-site* et le navigateur cessera d'envoyer ce cookie
# avec `Lax` : plus aucun refresh ne fonctionnera, et les utilisateurs seront
# déconnectés au bout de la durée de vie de l'access token, SANS message d'erreur
# explicite côté serveur. Il faudra alors passer JWT_REFRESH_COOKIE_SAMESITE à
# "None" — ce qui EXIGE `Secure=True` (donc HTTPS de bout en bout) et des origines
# CORS explicites (CORS_ALLOW_ALL_ORIGINS doit rester False).
JWT_REFRESH_COOKIE_SAMESITE = env.str("JWT_REFRESH_COOKIE_SAMESITE", default="Lax")

# En dev, le front tourne en HTTP simple : un cookie `Secure` ne serait jamais
# posé. Forcé à True en production (config/django/production.py).
JWT_REFRESH_COOKIE_SECURE = env.bool("JWT_REFRESH_COOKIE_SECURE", default=False)

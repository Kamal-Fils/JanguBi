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

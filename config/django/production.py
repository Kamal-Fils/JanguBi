from config.env import env

from .base import *  # noqa

DEBUG = env.bool("DJANGO_DEBUG", default=False)

SECRET_KEY = env("SECRET_KEY")

# En production, les statiques sont servis par WhiteNoise avec MANIFEST
# (cache-busting via noms hashés) + compression gzip/brotli. Le collectstatic
# est exécuté AU BUILD (docker/production.Dockerfile), donc le manifest existe
# déjà dans l'image. On n'active ce storage strict QU'en prod : le dev reste sur
# le storage par défaut (pas de manifest requis sans collectstatic).
STORAGES = {
    **STORAGES,  # noqa: F405 — défini dans config/settings/files_and_storages.py
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Traefik passe X-Forwarded-Host; accepter aussi le container name "django"
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["django", "localhost", "127.0.0.1"])

CORS_ALLOW_ALL_ORIGINS = env.bool("CORS_ALLOW_ALL_ORIGINS", default=False)
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ORIGIN_WHITELIST = env.list(
    "DJANGO_CORS_ORIGIN_WHITELIST",
    default=env.list("CORS_ORIGIN_WHITELIST", default=[]),
)
CORS_ALLOWED_ORIGIN_REGEXES = env.list("CORS_ALLOWED_ORIGIN_REGEXES", default=[])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# Origins autorisées au handshake WebSocket (config/asgi.py). L'Origin envoyée par
# le navigateur est le domaine du FRONT — qui n'est pas dans ALLOWED_HOSTS (domaine
# API) — donc AllowedHostsOriginValidator rejetait tous les WS en prod. À défaut de
# WS_ALLOWED_ORIGINS explicite, on réutilise CORS_ALLOWED_ORIGINS (même liste de
# fronts de confiance).
WS_ALLOWED_ORIGINS = env.list(
    "WS_ALLOWED_ORIGINS",
    default=env.list("CORS_ALLOWED_ORIGINS", default=[]),
)

SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=True)

# https://docs.djangoproject.com/en/dev/ref/settings/#secure-proxy-ssl-header
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-ssl-redirect
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=False)
# https://docs.djangoproject.com/en/dev/ref/middleware/#x-content-type-options-nosniff
SECURE_CONTENT_TYPE_NOSNIFF = env.bool("SECURE_CONTENT_TYPE_NOSNIFF", default=True)

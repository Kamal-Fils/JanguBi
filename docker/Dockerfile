# syntax=docker/dockerfile:1
# ─────────────────────────────────────────────────────────────────────────────
# Image Python multi-stage pour JanguBi (backend Django).
#
# Un SEUL fichier, plusieurs "stages" (étages). On choisit lequel construire avec
#   docker build --target production ...
#   docker build --target development ...
#
# Idée du multi-stage : on COMPILE les dépendances dans un étage jetable
# (avec gcc, headers, etc. — ~300 Mo d'outils), puis on COPIE seulement le
# résultat (le venv) dans une image finale minuscule. Les outils de build ne
# se retrouvent JAMAIS dans l'image qu'on déploie → plus légère + plus sûre.
# ─────────────────────────────────────────────────────────────────────────────


# ═══════════════════════════════════════════════════════════════════════════
# STAGE 1 — base : le socle commun (runtime Python minimal)
# ═══════════════════════════════════════════════════════════════════════════
# "slim" = variante Debian allégée de l'image Python officielle (~120 Mo vs
# ~1 Go pour la full). Elle n'a PAS les outils de compilation — on les ajoutera
# uniquement dans le builder.
FROM python:3.12.4-slim AS base

# Variables d'environnement valables dans TOUS les étages qui héritent de `base`.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
#   PYTHONUNBUFFERED=1        → logs Python affichés immédiatement (pas de buffer)
#   PYTHONDONTWRITEBYTECODE=1 → pas de fichiers .pyc inutiles dans l'image
#   PIP_NO_CACHE_DIR=1        → pip ne garde pas son cache → image plus petite
#   VIRTUAL_ENV + PATH        → on "active" le venv : tout `python`/`pip` pointe
#                               vers /opt/venv (le venv qu'on copiera du builder)

# Librairies SYSTÈME nécessaires à l'EXÉCUTION (pas au build) :
#   libpq5   → client PostgreSQL, requis par psycopg2 quand il TOURNE
#   libgomp1 → OpenMP, requis par onnxruntime (moteur de fastembed) au runtime
# --no-install-recommends évite des paquets superflus ; on purge la liste apt
# dans la MÊME couche pour ne pas la garder dans l'image.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*


# ═══════════════════════════════════════════════════════════════════════════
# STAGE 2 — builder : compile + installe les dépendances de PROD dans un venv
# ═══════════════════════════════════════════════════════════════════════════
FROM base AS builder

# Outils de BUILD (lourds). Ils restent dans CE stage et ne polluent pas l'image
# finale :
#   build-essential → gcc, make… (pour compiler psycopg2 qui n'a pas de wheel)
#   libpq-dev       → en-têtes PostgreSQL (pour compiler psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# uv : installeur de paquets ultra-rapide (par les créateurs de ruff), 10-100×
# plus vite que pip. On l'installe sur le python SYSTÈME *avant* de créer le venv
# → il atterrit dans /usr/local (pas dans /opt/venv), donc il n'est PAS copié
# dans l'image finale. Il sert seulement à remplir le venv ci-dessous.
RUN pip install --no-cache-dir uv

# On crée un environnement virtuel isolé. C'est juste un dossier (/opt/venv) qui
# contient un python + tous les packages installés. On le copiera tel quel.
RUN python -m venv "$VIRTUAL_ENV"

# On copie d'ABORD seulement les fichiers de requirements. Tant qu'ils ne
# changent pas, Docker REUTILISE le cache de la couche d'install ci-dessous
# (gros gain de temps : on ne réinstalle pas tout à chaque changement de code).
COPY requirements/ requirements/

# Dépendances de PRODUCTION uniquement (base.txt). uv installe dans le venv actif
# (VIRTUAL_ENV est exporté dans le stage `base`).
RUN uv pip install -r requirements/base.txt


# ═══════════════════════════════════════════════════════════════════════════
# STAGE 3 — builder-dev : AJOUTE les dépendances de DÉVELOPPEMENT au venv
# ═══════════════════════════════════════════════════════════════════════════
# Hérite du builder (donc base.txt déjà installé + en cache) et ajoute local.txt
# (pytest, mypy, ruff, ipython, debug-toolbar, stubs…). local.txt fait `-r base.txt`
# mais comme c'est déjà installé, pip ne réinstalle que le supplément.
FROM builder AS builder-dev
RUN uv pip install -r requirements/local.txt


# ═══════════════════════════════════════════════════════════════════════════
# STAGE 4 — production : IMAGE FINALE légère (aucun outil de build)
# ═══════════════════════════════════════════════════════════════════════════
FROM base AS production

# Utilisateur non-root (sécurité) : si le process est compromis, l'attaquant
# n'est pas root dans le conteneur. --uid 1000 = même uid que l'utilisateur hôte
# habituel (utile si un volume est monté).
RUN useradd --create-home --uid 1000 appuser

# On récupère le venv DÉJÀ construit dans le builder — sans gcc ni headers.
# C'est LE cœur du multi-stage : on prend le résultat, pas l'atelier.
COPY --from=builder $VIRTUAL_ENV $VIRTUAL_ENV

# Entrypoint copié HORS de /app : en local le code est bind-monté sur /app, ce
# qui écraserait un entrypoint placé dedans. On le strip des éventuels \r Windows
# et on le rend exécutable.
COPY entrypoint.sh /docker-entrypoint.sh
RUN sed -i 's/\r$//' /docker-entrypoint.sh && chmod +x /docker-entrypoint.sh

WORKDIR /app
# Le code applicatif (respecte .dockerignore : pas de .venv/.git/.env…).
# `--chown` pose la bonne propriété EN MÊME TEMPS que la copie → une seule couche.
# (Un `RUN chown -R` après coup recopierait tout /app dans une couche en double.)
COPY --chown=appuser:appuser . /app

# On bascule sur l'utilisateur non-root pour la suite + l'exécution.
USER appuser

# L'entrypoint applique les migrations puis exécute la commande (CMD ou celle du
# docker-compose). En prod on sert l'app ASGI avec Daphne (WebSocket/Channels).
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]


# ═══════════════════════════════════════════════════════════════════════════
# STAGE 5 — development : image de DEV (venv avec outils + root pour le confort)
# ═══════════════════════════════════════════════════════════════════════════
FROM base AS development

# On récupère le venv COMPLET (base + outils dev) depuis builder-dev.
COPY --from=builder-dev $VIRTUAL_ENV $VIRTUAL_ENV

COPY entrypoint.sh /docker-entrypoint.sh
RUN sed -i 's/\r$//' /docker-entrypoint.sh && chmod +x /docker-entrypoint.sh

WORKDIR /app
# En dev, docker-compose bind-monte le code sur /app (ce COPY n'est qu'un repli
# si on lance l'image sans volume). On reste ROOT en dev : pas de soucis de
# permissions avec le volume monté, et on peut pip-install à la volée.
COPY . /app

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

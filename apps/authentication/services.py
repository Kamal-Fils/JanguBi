"""
Services d'authentification — JWT (drf_jwt / rest_framework_jwt).
"""

import logging

from django.db import transaction

from apps.users.enums import AuditEvent
from apps.users.models import BaseUser, SecurityAuditLog

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Handlers drf_jwt (référencés dans config/settings/jwt.py via dotted string)
# ---------------------------------------------------------------------------

def auth_user_get_jwt_secret_key(user: BaseUser) -> str:
    """
    Clé secrète par utilisateur = SECRET_KEY + jwt_key UUID.
    Permet d'invalider tous les tokens d'un utilisateur en tournant jwt_key.
    Référencé par JWT_AUTH['JWT_GET_USER_SECRET_KEY'] dans jwt.py.
    """
    from django.conf import settings
    return f"{settings.SECRET_KEY}{user.jwt_key}"


def auth_jwt_response_payload_handler(token: str, user: BaseUser | None = None, request=None) -> dict:
    """
    Enrichit la réponse JWT avec les données utilisateur basiques.
    Référencé par JWT_AUTH['JWT_RESPONSE_PAYLOAD_HANDLER'] dans jwt.py.
    """
    assert user is not None  # toujours fourni par le handler JWT
    return {
        "token": token,
        "user": {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "is_admin": user.is_admin,
        },
    }


def auth_logout(user: BaseUser, ip: str | None = None) -> None:
    """
    Enregistre l'événement de déconnexion dans l'audit log.
    La révocation du refresh token est gérée dans l'API (blacklist simplejwt).
    Pas de @transaction.atomic : l'audit log ne doit pas être couplé à la transaction du caller.
    """
    try:
        SecurityAuditLog.objects.create(
            user=user,
            event=AuditEvent.LOGOUT,
            ip_address=ip,
        )
    except Exception:
        logger.exception("Impossible d'enregistrer l'audit de déconnexion.")


@transaction.atomic
def auth_logout_all_devices(user: BaseUser, ip: str | None = None) -> None:
    """
    Déconnecte l'utilisateur de tous ses appareils via rotation du jwt_key.
    Tous les tokens JWT existants deviennent instantanément invalides,
    même s'ils ne sont pas encore expirés.
    """
    user.rotate_jwt_key()

    try:
        SecurityAuditLog.objects.create(
            user=user,
            event=AuditEvent.LOGOUT,
            ip_address=ip,
            metadata={"scope": "all_devices"},
        )
    except Exception:
        logger.exception("Impossible d'enregistrer l'audit de déconnexion globale.")

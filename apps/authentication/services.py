"""
Services d'authentification — JWT (djangorestframework-simplejwt).

La révocation globale repose sur BaseUser.jwt_key (UUID rotatif) : la claim est
injectée au login (CustomTokenObtainPairSerializer) et vérifiée à chaque requête
par JwtKeyEnforcingJWTAuthentication (REST) et le middleware WebSocket.
"""

import logging

from django.db import transaction

from apps.users.enums import AuditEvent
from apps.users.models import BaseUser, SecurityAuditLog

logger = logging.getLogger(__name__)


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

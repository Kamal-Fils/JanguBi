"""
Selectors utilisateurs — toute la logique de lecture.
Aucune logique d'écriture ici.
"""

from typing import Optional

from django.db.models.query import QuerySet

from apps.common.utils import get_object
from apps.users.filters import BaseUserFilter
from apps.users.models import BaseUser, Profile, SecurityAuditLog

# ---------------------------------------------------------------------------
# Données de connexion (réponse /me/)
# ---------------------------------------------------------------------------

def user_get_login_data(*, user: BaseUser) -> dict:
    """Données renvoyées après login ou via /api/auth/me/."""
    profile_data = {}
    if hasattr(user, "profile"):
        p = user.profile
        profile_data = {
            "first_name": p.first_name,
            "last_name": p.last_name,
            "title": p.title,
            "phone": str(p.phone) if p.phone else None,
            "primary_parish": p.primary_parish,
            "avatar": p.avatar.url if p.avatar else None,
        }

    return {
        "id": user.id,
        "email": user.email,
        "phone_number": str(user.phone_number),
        "role": user.role,
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "is_admin": user.is_admin,
        "is_staff": user.is_staff,
        "profile": profile_data,
    }


# ---------------------------------------------------------------------------
# Récupération unitaire
# ---------------------------------------------------------------------------

def user_get(user_id: int) -> Optional[BaseUser]:
    return get_object(BaseUser, id=user_id)


def user_get_by_email(email: str) -> Optional[BaseUser]:
    return get_object(BaseUser, email__iexact=email)


def user_get_with_profile(user_id: int) -> Optional[BaseUser]:
    return (
        BaseUser.objects
        .select_related("profile")
        .filter(id=user_id)
        .first()
    )


# ---------------------------------------------------------------------------
# Liste avec filtres
# ---------------------------------------------------------------------------

def user_list(*, filters: dict | None = None) -> QuerySet[BaseUser]:
    filters = filters or {}
    qs = BaseUser.objects.select_related("profile").all()
    return BaseUserFilter(filters, qs).qs


def user_list_for_admin(*, filters: dict | None = None) -> QuerySet[BaseUser]:
    """Liste complète pour admin (inclut les inactifs et supprimés soft)."""
    filters = filters or {}
    qs = BaseUser.objects.select_related("profile").all()
    return BaseUserFilter(filters, qs).qs


# ---------------------------------------------------------------------------
# Profil
# ---------------------------------------------------------------------------

def profile_get(*, user: BaseUser) -> Optional[Profile]:
    return Profile.objects.filter(user=user).first()


# ---------------------------------------------------------------------------
# Audit logs
# ---------------------------------------------------------------------------

def audit_log_list(*, user: BaseUser, limit: int = 50) -> QuerySet[SecurityAuditLog]:
    """Historique des événements de sécurité d'un utilisateur."""
    return (
        SecurityAuditLog.objects
        .filter(user=user)
        .order_by("-created_at")[:limit]
    )

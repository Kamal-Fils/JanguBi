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

def _org_ref(obj) -> dict | None:
    """Référence légère {id, name} vers une entité territoriale (ou None)."""
    if obj is None:
        return None
    return {"id": obj.id, "name": obj.name}


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
            "primary_parish": _org_ref(p.primary_parish),
            "avatar": p.avatar.url if p.avatar else None,
        }

    return {
        "id": user.id,
        "email": user.email,
        "phone_number": str(user.phone_number),
        "role": user.role,
        "pastoral_role": user.pastoral_role,
        "onboarding_state": user.onboarding_state,
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "is_admin": user.is_admin,
        "is_staff": user.is_staff,
        "diocese": _org_ref(user.diocese),
        "province": _org_ref(user.province),
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

def user_list(*, filters: dict | None = None, for_user: BaseUser | None = None) -> QuerySet[BaseUser]:
    filters = filters or {}
    qs = BaseUser.objects.select_related("profile").all()
    qs = BaseUserFilter(filters, qs).qs
    if for_user is not None:
        # Cloisonnement territorial : un admin scopé ne gère que les utilisateurs de
        # ses paroisses (repli legacy si aucune affectation territoriale).
        from django.db.models import Q

        from apps.users.scoping import accessible_parish_ids, is_global_admin

        if not is_global_admin(for_user):
            parish_ids = accessible_parish_ids(for_user)
            if parish_ids:
                qs = qs.filter(
                    Q(profile__primary_parish_id__in=parish_ids) | Q(id=for_user.id)
                )
    return qs


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

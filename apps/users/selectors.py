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


def membership_ref(m) -> dict:
    """Représentation d'une appartenance pour /me : église/paroisse/diocèse + flag."""
    church = m.church
    parish = church.parish
    diocese = parish.diocese
    return {
        "id": m.id,
        "church": {"id": church.id, "name": church.name},
        "parish": {"id": parish.id, "name": parish.name},
        "diocese": {"id": diocese.id, "name": diocese.name},
        "is_primary": m.is_primary,
    }


def user_memberships_data(*, user: BaseUser) -> list[dict]:
    """Liste des appartenances de l'utilisateur (principale en tête)."""
    from apps.users.models import Membership

    qs = (
        Membership.objects.filter(user=user)
        .select_related("church__parish__diocese")
        .order_by("-is_primary", "created_at")
    )
    return [membership_ref(m) for m in qs]


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

    # Multi-appartenance (Chantier 2). Les SINGULIERS diocese/province/primary_parish
    # restent les "principaux" (rétro-compat front actuel) ; on AJOUTE les pluriels.
    memberships = user_memberships_data(user=user)
    church_ids = [m["church"]["id"] for m in memberships]
    parish_ids = list(dict.fromkeys(m["parish"]["id"] for m in memberships))
    diocese_ids = list(dict.fromkeys(m["diocese"]["id"] for m in memberships))

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
        "memberships": memberships,
        "church_ids": church_ids,
        "parish_ids": parish_ids,
        "diocese_ids": diocese_ids,
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
    # profile__primary_parish : la sortie users sérialise la paroisse principale en
    # {id, name} → select_related évite un N+1 (BUG-B1).
    qs = BaseUser.objects.select_related("profile", "profile__primary_parish").all()
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

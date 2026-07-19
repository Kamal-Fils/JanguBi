"""
Selectors utilisateurs — toute la logique de lecture.
Aucune logique d'écriture ici.
"""

import uuid
from typing import Optional

from django.db.models import Prefetch, Q
from django.db.models.query import QuerySet

from apps.common.utils import get_object
from apps.users.enums import ClergyValidationStatus, UserRole
from apps.users.filters import BaseUserFilter
from apps.users.models import (
    BaseUser,
    ClergySelfDeclaration,
    Profile,
    SecurityAuditLog,
)

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


def user_is_in_scope_of(*, target: BaseUser, admin: BaseUser) -> bool:
    """L'administrateur `admin` a-t-il autorité territoriale sur `target` ?

    **Fail-CLOSED** : un admin sans affectation territoriale n'a autorité sur
    PERSONNE (le repli historique « aucune affectation ⇒ tout le monde » était
    un fail-open ; cf. `apps/documents/selectors.py`, qui a corrigé le même
    anti-pattern). Un admin garde toujours autorité sur son propre compte.

    Un utilisateur sans paroisse principale (onboarding non terminé) n'est
    rattaché à aucun périmètre : seul un admin global peut agir sur lui.
    """
    from apps.users.scoping import accessible_parish_ids, is_global_admin

    if target.id == admin.id:
        return True
    if is_global_admin(admin):
        return True

    parish_ids = accessible_parish_ids(admin)  # set (jamais None : global déjà traité)
    if not parish_ids:
        return False

    target_parish_id = getattr(getattr(target, "profile", None), "primary_parish_id", None)
    if target_parish_id is None:
        return False
    return target_parish_id in parish_ids


def clergy_pending_validation_list(*, admin: BaseUser) -> QuerySet[BaseUser]:
    """Comptes clergé en attente de validation hiérarchique, dans le périmètre
    territorial de ``admin``.

    La file est adossée aux **auto-déclarations** (``ClergySelfDeclaration``), et
    non à ``pastoral_role`` : un candidat en attente est délibérément encore un
    laïc côté autorisations (cf. la docstring du modèle — écrire le rôle avant
    revue serait une escalade de privilèges). Les comptes issus d'une invitation
    naissent ``APPROVED`` : ils ne remontent jamais ici.

    Le cloisonnement porte sur la **paroisse revendiquée dans la demande**, pas
    sur la paroisse du profil : un candidat dont l'onboarding fidèle n'est pas
    terminé n'a pas de paroisse principale et serait sinon invisible de sa propre
    autorité — la file resterait vide côté évêque.

    **Fail-CLOSED**, cohérent avec ``user_is_in_scope_of`` et ``user_list`` : hors
    admin global, un validateur sans affectation territoriale ne voit RIEN.
    """
    from apps.users.scoping import accessible_parish_ids, is_global_admin

    pending_declarations = (
        ClergySelfDeclaration.objects
        .filter(status=ClergySelfDeclaration.Status.PENDING)
        .select_related("parish", "parish__diocese", "justification_file")
    )

    qs = (
        BaseUser.objects
        .select_related("profile", "profile__primary_parish", "diocese")
        .prefetch_related(
            Prefetch(
                "clergy_declarations",
                queryset=pending_declarations,
                to_attr="pending_declarations",
            )
        )
        .filter(
            clergy_declarations__status=ClergySelfDeclaration.Status.PENDING,
            clergy_validation_status=ClergyValidationStatus.PENDING,
        )
        .distinct()
        .order_by("created_at")
    )

    if is_global_admin(admin):
        return qs

    parish_ids = accessible_parish_ids(admin)  # set (jamais None : global déjà traité)
    if not parish_ids:
        return qs.none()
    return qs.filter(clergy_declarations__parish_id__in=parish_ids)


def clergy_declaration_current(*, user: BaseUser) -> Optional["ClergySelfDeclaration"]:
    """Dernière auto-déclaration du demandeur (état de suivi affiché côté fidèle).

    ``None`` s'il n'a jamais rien déposé. Une demande refusée reste visible : le
    demandeur doit pouvoir lire le motif pour corriger et resoumettre.
    """
    return (
        ClergySelfDeclaration.objects
        .filter(user=user)
        .select_related("parish", "parish__diocese", "justification_file")
        .order_by("-created_at")
        .first()
    )


def clergy_declaration_validator_emails(*, diocese_id: int | None) -> list[str]:
    """Emails des autorités compétentes pour trancher une demande de ce diocèse.

    Miroir de ``user_can_validate_clergy`` : les super_admins (compétents partout)
    et les évêques/archevêques porteurs d'une affectation active couvrant le
    diocèse concerné. Fail-closed : un évêque sans affectation territoriale ne
    reçoit rien, exactement comme il ne verrait rien dans la file.
    """
    from apps.users.enums import PastoralRole, RoleScope
    from apps.users.models import RoleAssignment

    emails = set(
        BaseUser.objects.filter(
            role=UserRole.SUPER_ADMIN, is_active=True
        ).values_list("email", flat=True)
    )

    if diocese_id is not None:
        from apps.org.models import Diocese

        province_id = (
            Diocese.objects.filter(pk=diocese_id)
            .values_list("province_id", flat=True)
            .first()
        )
        covering = Q(scope=RoleScope.DIOCESE, diocese_id=diocese_id)
        if province_id:
            covering |= Q(scope=RoleScope.PROVINCE, province_id=province_id)

        emails |= set(
            RoleAssignment.objects.filter(covering, is_active=True)
            .filter(
                user__is_active=True,
                user__pastoral_role__in=[PastoralRole.EVEQUE, PastoralRole.ARCHEVEQUE],
            )
            .values_list("user__email", flat=True)
        )

    return sorted(emails)


def user_get_by_email(email: str) -> Optional[BaseUser]:
    return get_object(BaseUser, email__iexact=email)


def user_get_with_profile(user_id: uuid.UUID | str | int) -> Optional[BaseUser]:
    # profile__primary_parish : la fiche détail sérialise la paroisse principale
    # en {id, name} → select_related évite une requête supplémentaire.
    return (
        BaseUser.objects
        .select_related("profile", "profile__primary_parish")
        .filter(id=user_id)  # type: ignore[misc]  # django-stubs limite le lookup UUIDField à UUID|str ; Django accepte aussi int (uuid.UUID(int=...))
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
            # Fail-CLOSED : sans affectation territoriale, l'admin ne voit que
            # son propre compte. L'ancien `if parish_ids:` sautait le filtre et
            # renvoyait TOUTE la plateforme — or aucun `RoleAssignment` n'est
            # créé par `user_create_by_admin`, donc c'était le cas courant.
            qs = qs.filter(
                Q(profile__primary_parish_id__in=parish_ids or [])
                | Q(id=for_user.id)
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
# Appartenances (lectures consommées par la couche API)
# ---------------------------------------------------------------------------

def membership_get(*, membership_id: int):
    """Une appartenance par ID, chaîne territoriale préchargée (``None`` si absente)."""
    from apps.users.models import Membership

    return (
        Membership.objects
        .select_related("church__parish__diocese")
        .filter(pk=membership_id)
        .first()
    )


def membership_list_by_ids(*, membership_ids: list[int]) -> QuerySet:
    """Recharge un lot d'appartenances avec leur chaîne territoriale.

    Les objets renvoyés par ``membership_create`` n'ont pas les FK préchargées :
    sans ce rechargement groupé, ``membership_ref`` déclenche un N+1.
    """
    from apps.users.models import Membership

    return (
        Membership.objects
        .select_related("church__parish__diocese")
        .filter(pk__in=membership_ids)
        .order_by("-is_primary", "created_at")
    )


# ---------------------------------------------------------------------------
# Audit logs
# ---------------------------------------------------------------------------

def audit_log_list(*, user: BaseUser) -> QuerySet[SecurityAuditLog]:
    """Historique des événements de sécurité d'un utilisateur.

    Renvoie un QuerySet NON tronqué : la pagination est du ressort de la couche
    API (``get_paginated_response``). Un slice ici empêcherait tout filtrage /
    pagination en aval (« Cannot filter a query once a slice has been taken »).
    """
    return (
        SecurityAuditLog.objects
        .filter(user=user)
        .order_by("-created_at")
    )

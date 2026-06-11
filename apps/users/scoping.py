"""
Autorité de scoping territorial (lecture seule).

Source de vérité du cloisonnement RBAC : qui peut administrer quoi, à quel
niveau territorial, en fonction de ses ``RoleAssignment`` actifs. Consommé par
les selectors et les classes de permission de toutes les apps.

Convention : les fonctions ``accessible_*_ids`` renvoient ``None`` pour signifier
« aucune restriction » (administrateur global / super_admin), ou un ``set`` d'IDs
autorisés sinon.
"""

from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.org.models import Church, Diocese, Parish
from apps.users.enums import PastoralRole, RoleScope, UserRole
from apps.users.models import BaseUser, RoleAssignment

# ---------------------------------------------------------------------------
# Scoping de contenu (multi-appartenance) — générique, réutilisable
# ---------------------------------------------------------------------------

# Vocabulaire de portée partagé par les contenus scopés (Article, Event, …).
# Doit rester aligné avec les ScopeType de chaque modèle (mêmes valeurs).
SCOPE_GLOBAL = "global"
SCOPE_DIOCESE = "diocese"
SCOPE_PARISH = "parish"
SCOPE_CHURCH = "church"


def get_scoped_queryset(qs: QuerySet, user) -> QuerySet:
    """Restreint ``qs`` (modèle scopé : ``scope_type`` + FK
    ``scope_church``/``scope_parish``/``scope_diocese``) à ce que ``user`` peut voir,
    d'après ses appartenances : global ∪ église∈church_ids ∪ paroisse∈parish_ids ∪
    diocèse∈diocese_ids. Helper générique consommé par les feeds (Article ici,
    Event au Chantier 3b)."""
    scope = user.get_scope_ids()
    filters = Q(scope_type=SCOPE_GLOBAL)
    if scope["church_ids"]:
        filters |= Q(scope_type=SCOPE_CHURCH, scope_church_id__in=scope["church_ids"])
    if scope["parish_ids"]:
        filters |= Q(scope_type=SCOPE_PARISH, scope_parish_id__in=scope["parish_ids"])
    if scope["diocese_ids"]:
        filters |= Q(scope_type=SCOPE_DIOCESE, scope_diocese_id__in=scope["diocese_ids"])
    return qs.filter(filters)


# ---------------------------------------------------------------------------
# Affectations actives
# ---------------------------------------------------------------------------

def active_role_assignments(user) -> QuerySet[RoleAssignment]:
    if not user or not getattr(user, "is_authenticated", False):
        return RoleAssignment.objects.none()
    return user.role_assignments.filter(is_active=True)


def is_global_admin(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "role", None) == UserRole.SUPER_ADMIN:
        return True
    return active_role_assignments(user).filter(role=UserRole.SUPER_ADMIN).exists()


# Rôles d'administration digitale (UserRole). Source de vérité = RoleAssignment :
# un curé porteur d'une RoleAssignment(parish_admin) est admin même si user.role
# est resté 'fidele'.
_ANY_ADMIN_ROLES = {
    UserRole.SUPER_ADMIN,
    UserRole.PROVINCE_ADMIN,
    UserRole.DIOCESE_ADMIN,
    UserRole.PARISH_ADMIN,
    UserRole.CHURCH_ADMIN,
}


def is_any_admin(user) -> bool:
    """Vrai si l'utilisateur possède une capacité admin, par ``user.role`` OU par
    une ``RoleAssignment`` admin active. Permet aux endpoints view-level d'admettre
    le clergé scopé (curé avec RoleAssignment, user.role='fidele') ; l'autorité
    territoriale fine reste décidée par ``user_can_admin_*`` / ``accessible_*_ids``.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "role", None) in _ANY_ADMIN_ROLES:
        return True
    return active_role_assignments(user).filter(role__in=_ANY_ADMIN_ROLES).exists()


def role_assignment_list(*, user=None) -> QuerySet[RoleAssignment]:
    qs = RoleAssignment.objects.select_related(
        "user", "province", "diocese", "parish", "church", "granted_by"
    )
    if user is not None:
        qs = qs.filter(user=user)
    return qs.order_by("-created_at")


# ---------------------------------------------------------------------------
# Ensembles d'IDs accessibles (None = illimité)
# ---------------------------------------------------------------------------

def accessible_province_ids(user) -> set[int] | None:
    if is_global_admin(user):
        return None
    ids = set(
        active_role_assignments(user)
        .filter(scope=RoleScope.PROVINCE)
        .values_list("province_id", flat=True)
    )
    ids.discard(None)
    return ids


def accessible_diocese_ids(user) -> set[int] | None:
    if is_global_admin(user):
        return None
    ras = active_role_assignments(user)
    diocese_ids = set(ras.filter(scope=RoleScope.DIOCESE).values_list("diocese_id", flat=True))
    province_ids = set(ras.filter(scope=RoleScope.PROVINCE).values_list("province_id", flat=True))
    province_ids.discard(None)
    if province_ids:
        diocese_ids |= set(
            Diocese.objects.filter(province_id__in=province_ids).values_list("id", flat=True)
        )
    diocese_ids.discard(None)
    return diocese_ids


def accessible_parish_ids(user) -> set[int] | None:
    if is_global_admin(user):
        return None
    ras = active_role_assignments(user)
    parish_ids = set(ras.filter(scope=RoleScope.PARISH).values_list("parish_id", flat=True))
    church_ids = set(ras.filter(scope=RoleScope.CHURCH).values_list("church_id", flat=True))
    church_ids.discard(None)
    if church_ids:
        parish_ids |= set(
            Church.objects.filter(id__in=church_ids).values_list("parish_id", flat=True)
        )
    diocese_ids = accessible_diocese_ids(user)  # set (jamais None ici)
    if diocese_ids:
        parish_ids |= set(
            Parish.objects.filter(diocese_id__in=diocese_ids).values_list("id", flat=True)
        )
    parish_ids.discard(None)
    return parish_ids


# ---------------------------------------------------------------------------
# Vérifications ponctuelles d'autorité
# ---------------------------------------------------------------------------

def user_can_admin_parish(user, parish_id: int) -> bool:
    if is_global_admin(user):
        return True
    try:
        parish = Parish.objects.select_related("diocese").get(id=parish_id)
    except Parish.DoesNotExist:
        return False
    ras = active_role_assignments(user)
    if ras.filter(scope=RoleScope.PARISH, parish_id=parish_id).exists():
        return True
    if ras.filter(scope=RoleScope.DIOCESE, diocese_id=parish.diocese_id).exists():
        return True
    if ras.filter(scope=RoleScope.PROVINCE, province_id=parish.diocese.province_id).exists():
        return True
    return False


def user_can_admin_church(user, church_id: int) -> bool:
    """Autorité sur une église X (RG-CONT Chantier 3b). Vrai si :
    admin global, OU RoleAssignment scope=church sur X, OU autorité sur la PAROISSE
    de X (parish/diocese/province au-dessus). → un church_admin scopé sur X PEUT
    publier sur X, sans exiger l'autorité paroisse."""
    if is_global_admin(user):
        return True
    try:
        church = Church.objects.select_related("parish").get(id=church_id)
    except Church.DoesNotExist:
        return False
    if active_role_assignments(user).filter(
        scope=RoleScope.CHURCH, church_id=church_id
    ).exists():
        return True
    return user_can_admin_parish(user, church.parish_id)


def user_can_admin_diocese(user, diocese_id: int) -> bool:
    if is_global_admin(user):
        return True
    try:
        diocese = Diocese.objects.get(id=diocese_id)
    except Diocese.DoesNotExist:
        return False
    ras = active_role_assignments(user)
    if ras.filter(scope=RoleScope.DIOCESE, diocese_id=diocese_id).exists():
        return True
    if ras.filter(scope=RoleScope.PROVINCE, province_id=diocese.province_id).exists():
        return True
    return False


def user_can_admin_province(user, province_id: int) -> bool:
    if is_global_admin(user):
        return True
    return active_role_assignments(user).filter(
        scope=RoleScope.PROVINCE, province_id=province_id
    ).exists()


# ---------------------------------------------------------------------------
# Clergé d'un territoire & chaîne de supériorité
# ---------------------------------------------------------------------------

def parish_principal_cure(parish_id: int) -> BaseUser | None:
    ra = (
        RoleAssignment.objects.filter(
            parish_id=parish_id,
            scope=RoleScope.PARISH,
            is_principal=True,
            is_active=True,
        )
        .select_related("user")
        .first()
    )
    return ra.user if ra else None


def clergy_of_parish(parish_id: int) -> QuerySet[BaseUser]:
    church_ids = list(Church.objects.filter(parish_id=parish_id).values_list("id", flat=True))
    user_ids = (
        RoleAssignment.objects.filter(is_active=True)
        .filter(
            Q(scope=RoleScope.PARISH, parish_id=parish_id)
            | Q(scope=RoleScope.CHURCH, church_id__in=church_ids)
        )
        .values_list("user_id", flat=True)
    )
    return BaseUser.objects.filter(id__in=set(user_ids))


def clergy_of_diocese(diocese_id: int) -> QuerySet[BaseUser]:
    parish_ids = list(Parish.objects.filter(diocese_id=diocese_id).values_list("id", flat=True))
    church_ids = list(
        Church.objects.filter(parish__diocese_id=diocese_id).values_list("id", flat=True)
    )
    user_ids = (
        RoleAssignment.objects.filter(is_active=True)
        .filter(
            Q(scope=RoleScope.DIOCESE, diocese_id=diocese_id)
            | Q(scope=RoleScope.PARISH, parish_id__in=parish_ids)
            | Q(scope=RoleScope.CHURCH, church_id__in=church_ids)
        )
        .values_list("user_id", flat=True)
    )
    return BaseUser.objects.filter(id__in=set(user_ids))


def _primary_parish_id(user) -> int | None:
    try:
        return user.profile.primary_parish_id
    except Exception:
        return None


def _diocese_bishop(diocese_id: int) -> BaseUser | None:
    ra = (
        RoleAssignment.objects.filter(
            scope=RoleScope.DIOCESE, diocese_id=diocese_id, is_active=True
        )
        .select_related("user")
        .first()
    )
    if ra:
        return ra.user
    return BaseUser.objects.filter(
        pastoral_role=PastoralRole.EVEQUE, diocese_id=diocese_id
    ).first()


def _province_archbishop(province_id: int) -> BaseUser | None:
    ra = (
        RoleAssignment.objects.filter(
            scope=RoleScope.PROVINCE, province_id=province_id, is_active=True
        )
        .select_related("user")
        .first()
    )
    if ra:
        return ra.user
    return BaseUser.objects.filter(
        pastoral_role=PastoralRole.ARCHEVEQUE, province_id=province_id
    ).first()


def superior_of(user) -> BaseUser | None:
    """
    Supérieur hiérarchique :
    fidèle → curé principal de sa paroisse ;
    curé (parish-scope) → doyen du doyenné si défini, sinon évêque du diocèse ;
    évêque / diocese-scope → archevêque de la province ;
    archevêque / province-scope → aucun (None).
    """
    if not user or not getattr(user, "is_authenticated", False):
        return None

    ras = active_role_assignments(user)

    diocese_ra = ras.filter(scope=RoleScope.DIOCESE).select_related("diocese").first()
    if diocese_ra and diocese_ra.diocese_id:
        return _province_archbishop(diocese_ra.diocese.province_id)

    if getattr(user, "pastoral_role", None) == PastoralRole.EVEQUE and user.province_id:
        return _province_archbishop(user.province_id)

    parish_ra = (
        ras.filter(scope=RoleScope.PARISH)
        .select_related("parish__deanery", "parish__diocese")
        .first()
    )
    if parish_ra and parish_ra.parish_id:
        parish = parish_ra.parish
        if parish.deanery_id and parish.deanery.dean_id:
            return parish.deanery.dean
        return _diocese_bishop(parish.diocese_id)

    primary_parish_id = _primary_parish_id(user)
    if primary_parish_id:
        cure = parish_principal_cure(primary_parish_id)
        if cure:
            return cure
        try:
            diocese_id = Parish.objects.values_list("diocese_id", flat=True).get(id=primary_parish_id)
            return _diocese_bishop(diocese_id)
        except Parish.DoesNotExist:
            return None
    return None

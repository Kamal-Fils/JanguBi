from rest_framework.permissions import BasePermission

from apps.users.enums import PastoralRole, UserOnboardingState, UserRole

_ADMIN_ROLES = {
    UserRole.SUPER_ADMIN,
    UserRole.PROVINCE_ADMIN,
    UserRole.DIOCESE_ADMIN,
    UserRole.PARISH_ADMIN,
    UserRole.CHURCH_ADMIN,
}

_CLERGY_PASTORAL_ROLES = {
    PastoralRole.DIACRE,
    PastoralRole.PRETRE,
    PastoralRole.EVEQUE,
    PastoralRole.ARCHEVEQUE,
}

# Administration de niveau diocèse et au-dessus. Strictement plus restrictif que
# ``IsAnyAdmin`` : exclut parish_admin / church_admin (curé, diacre, vicaire).
_DIOCESE_AND_ABOVE_ROLES = {
    UserRole.SUPER_ADMIN,
    UserRole.PROVINCE_ADMIN,
    UserRole.DIOCESE_ADMIN,
}


class IsSuperAdmin(BasePermission):
    """Réservé au rôle super_admin uniquement."""

    message = "Accès réservé au Super Admin."

    def has_permission(self, request, view) -> bool:
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == UserRole.SUPER_ADMIN
        )


class IsAnyAdmin(BasePermission):
    """Autorise tout administrateur — par ``user.role`` OU par une ``RoleAssignment``
    admin active (source de vérité). Permet au clergé scopé (curé avec
    RoleAssignment, ``user.role='fidele'``) d'atteindre les endpoints admin ;
    l'autorité territoriale fine reste tranchée au niveau objet/selector."""

    message = "Accès réservé aux administrateurs."

    def has_permission(self, request, view) -> bool:
        from apps.users.scoping import is_any_admin

        return is_any_admin(request.user)


class IsDioceseAdminOrAbove(BasePermission):
    """Réservé aux administrateurs de niveau diocèse et au-dessus.

    Autorise ``role ∈ {super_admin, province_admin, diocese_admin}`` — par
    ``user.role`` OU par une ``RoleAssignment`` active de ce niveau (source de
    vérité, comme ``IsAnyAdmin``). Exclut explicitement parish_admin et
    church_admin : la gestion des comptes utilisateurs (liste, activation,
    suppression soft, journaux d'audit) n'est pas une compétence paroissiale.
    """

    message = "Accès réservé aux administrateurs de diocèse et au-dessus."

    def has_permission(self, request, view) -> bool:
        from apps.users.scoping import active_role_assignments

        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.role in _DIOCESE_AND_ABOVE_ROLES:
            return True
        return active_role_assignments(user).filter(role__in=_DIOCESE_AND_ABOVE_ROLES).exists()


class IsClergyValidator(BasePermission):
    """Autorité habilitée à trancher les demandes de compte clergé.

    Miroir backend de ``canManageClergy`` côté front et de
    ``_can_manage_invitations`` (apps.clergy_accounts.apis) : super_admin OU
    évêque/archevêque. C'est un filtre de niveau vue — l'autorité territoriale
    fine (le diocèse concerné) reste tranchée dans les services, fail-closed.
    """

    message = "Accès réservé aux autorités habilitées à valider le clergé."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.role == UserRole.SUPER_ADMIN:
            return True
        return user.pastoral_role in {PastoralRole.EVEQUE, PastoralRole.ARCHEVEQUE}


class IsFidele(BasePermission):
    """Autorise tout utilisateur authentifié (fidèle ou admin)."""

    message = "Authentification requise."

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated)


class IsOwnerOrAdmin(BasePermission):
    """
    Autorisation au niveau objet :
    - L'objet est accessible par son propriétaire (user == request.user)
    - Ou par n'importe quel rôle admin
    """

    message = "Vous n'avez pas la permission d'accéder à cette ressource."

    def has_object_permission(self, request, view, obj) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.role in _ADMIN_ROLES:
            return True
        if hasattr(obj, "user"):
            return obj.user == request.user
        return obj == request.user


class IsOnboardingCompleted(BasePermission):
    """Garde canonique des écritures territoriales du fidèle.

    Autorise si l'onboarding est terminé (le fidèle a choisi sa/ses paroisse(s)),
    OU si l'utilisateur est admin (RoleAssignment — source de vérité), OU s'il est
    clergé (pastoral_role) : le clergé écrit via sa RoleAssignment, pas via
    l'onboarding fidèle — ``invitation_accept`` ne pose jamais ``completed``.
    """

    message = (
        "Veuillez finaliser votre inscription (choisir votre paroisse) "
        "avant d'effectuer cette action."
    )

    def has_permission(self, request, view) -> bool:
        from apps.users.scoping import is_any_admin

        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.onboarding_state == UserOnboardingState.COMPLETED:
            return True
        if is_any_admin(user):
            return True
        return user.pastoral_role in _CLERGY_PASTORAL_ROLES


# Alias de compatibilité : IsAdminUser = super admin uniquement (pas tous les admins).
# Préférer IsAnyAdmin pour les endpoints accessibles à tous les rôles admin.
IsAdminUser = IsSuperAdmin
IsStaffOrAdminUser = IsAnyAdmin

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

from rest_framework.permissions import BasePermission

from apps.users.enums import UserRole

_ADMIN_ROLES = {
    UserRole.SUPER_ADMIN,
    UserRole.PROVINCE_ADMIN,
    UserRole.DIOCESE_ADMIN,
    UserRole.PARISH_ADMIN,
    UserRole.CHURCH_ADMIN,
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
    """Autorise tous les rôles admin (province, diocèse, paroisse, église, super)."""

    message = "Accès réservé aux administrateurs."

    def has_permission(self, request, view) -> bool:
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in _ADMIN_ROLES
        )


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


# Aliases pour compatibilité avec les imports existants dans apis.py
IsAdminUser = IsSuperAdmin
IsStaffOrAdminUser = IsAnyAdmin

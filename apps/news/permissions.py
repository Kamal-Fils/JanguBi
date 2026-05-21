from rest_framework.permissions import BasePermission

from apps.users.enums import UserRole

_EDITOR_ROLES = {
    UserRole.SUPER_ADMIN,
    UserRole.PROVINCE_ADMIN,
    UserRole.DIOCESE_ADMIN,
    UserRole.PARISH_ADMIN,
    UserRole.CHURCH_ADMIN,
}

_UNPUBLISH_ROLES = {
    UserRole.SUPER_ADMIN,
    UserRole.PROVINCE_ADMIN,
    UserRole.DIOCESE_ADMIN,
    UserRole.PARISH_ADMIN,
}


class IsArticleEditor(BasePermission):
    """Autorise les rôles pouvant créer / modifier / publier des articles."""

    message = "Seuls les administrateurs peuvent gérer les articles."

    def has_permission(self, request, view) -> bool:
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in _EDITOR_ROLES
        )


class CanUnpublishArticle(BasePermission):
    """Autorise les rôles pouvant dépublier un article (church_admin exclu)."""

    message = "Vous n'avez pas la permission de dépublier cet article."

    def has_permission(self, request, view) -> bool:
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in _UNPUBLISH_ROLES
        )

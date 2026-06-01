from rest_framework.permissions import BasePermission

from apps.news.services import is_news_editor
from apps.users.enums import UserRole

_UNPUBLISH_ROLES = {
    UserRole.SUPER_ADMIN,
    UserRole.PROVINCE_ADMIN,
    UserRole.DIOCESE_ADMIN,
    UserRole.PARISH_ADMIN,
}


class IsArticleEditor(BasePermission):
    """Autorise les rôles pouvant créer / modifier / publier des articles (admin OU clergé).

    Délègue à ``is_news_editor`` (apps.news.services) — source unique partagée
    avec la couche service — pour que le clergé identifié par ``pastoral_role``
    (role admin resté ``fidele``) ne soit pas bloqué à l'API.
    """

    message = "Seuls les administrateurs et le clergé peuvent gérer les articles."

    def has_permission(self, request, view) -> bool:
        return bool(
            request.user
            and request.user.is_authenticated
            and is_news_editor(request.user)
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

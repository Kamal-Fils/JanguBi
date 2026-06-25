from rest_framework.permissions import BasePermission

from apps.spiritual.services import is_reflection_editor


class IsReflectionEditor(BasePermission):
    """Autorise le clergé publicateur (prêtre/évêque/archevêque) et les admins à
    publier/éditer une réflexion. Source unique partagée avec la couche service."""

    message = "Seul le clergé (prêtre, évêque, archevêque) peut publier une réflexion."

    def has_permission(self, request, view) -> bool:
        return bool(
            request.user
            and request.user.is_authenticated
            and is_reflection_editor(request.user)
        )

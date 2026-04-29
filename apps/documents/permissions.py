from rest_framework.permissions import BasePermission

from apps.users.enums import UserRole

_ADMIN_ROLES = {
    UserRole.SUPER_ADMIN,
    UserRole.PROVINCE_ADMIN,
    UserRole.DIOCESE_ADMIN,
    UserRole.PARISH_ADMIN,
    UserRole.CHURCH_ADMIN,
}


class IsDocumentRequester(BasePermission):
    message = "Vous n'êtes pas le demandeur de cette demande."

    def has_object_permission(self, request, view, obj) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        return obj.requester_id == request.user.id


class IsDocumentRequesterOrAdmin(BasePermission):
    message = "Accès refusé."

    def has_object_permission(self, request, view, obj) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.role in _ADMIN_ROLES:
            return True
        return obj.requester_id == request.user.id

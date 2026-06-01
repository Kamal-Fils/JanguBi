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
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if obj.requester_id == user.id:
            return True
        # Admin : autorité territoriale RÉELLE sur la paroisse de la demande
        # (RoleAssignment), pas un simple user.role global. Ferme la lecture
        # inter-paroisses : un parish_admin de A ne voit pas une demande de B.
        from apps.documents.selectors import _request_effective_parish_id
        from apps.users.scoping import is_global_admin, user_can_admin_parish

        if is_global_admin(user):
            return True
        parish_id = _request_effective_parish_id(obj)
        return parish_id is not None and user_can_admin_parish(user, parish_id)

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.users.permissions import IsSuperAdmin


class IsSuperAdminOrReadOnly(BasePermission):
    """Lecture publique ; écriture réservée au Super Admin.

    Le catalogue TV (vidéos & catégories) est une configuration globale de la
    plateforme : sa modification est réservée au Super Admin (``role ==
    super_admin``), au même titre que le CRUD territorial (``apps/org``) et les
    endpoints de diagnostic (``apps/errors``). On ne se base PLUS sur
    ``is_staff`` (que tout compte admin digital possède).
    """

    message = "Accès réservé au Super Admin."

    def has_permission(self, request, view) -> bool:
        if request.method in SAFE_METHODS:
            return True
        return IsSuperAdmin().has_permission(request, view)

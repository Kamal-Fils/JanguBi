from typing import Optional
from uuid import UUID

from django.db.models import Q, QuerySet

from apps.core.exceptions import ApplicationError
from apps.documents.models import (
    DocumentRequest,
    DocumentRequestAttachment,
    DocumentRequestStatusLog,
    InternalNote,
)
from apps.users.enums import UserRole
from apps.users.models import BaseUser

_ADMIN_ROLES = {
    UserRole.SUPER_ADMIN,
    UserRole.PROVINCE_ADMIN,
    UserRole.DIOCESE_ADMIN,
    UserRole.PARISH_ADMIN,
    UserRole.CHURCH_ADMIN,
}


def document_request_list(*, user: BaseUser, filters: Optional[dict] = None) -> QuerySet[DocumentRequest]:
    filters = filters or {}
    qs = DocumentRequest.objects.select_related("requester", "assigned_to", "target_parish")

    if user.role not in _ADMIN_ROLES:
        qs = qs.filter(requester=user)
    else:
        # Cloisonnement territorial : un admin scopé (curé, admin diocèse…) ne voit
        # que les demandes de ses paroisses. Repli legacy si aucune affectation.
        from apps.users.scoping import accessible_parish_ids, is_global_admin

        if not is_global_admin(user):
            parish_ids = accessible_parish_ids(user)
            if parish_ids:
                qs = qs.filter(
                    Q(target_parish_id__in=parish_ids)
                    | Q(requester__profile__primary_parish_id__in=parish_ids)
                )

    if status := filters.get("status"):
        qs = qs.filter(status=status)
    if document_type := filters.get("document_type"):
        qs = qs.filter(document_type=document_type)
    if parish_name := filters.get("parish_name"):
        qs = qs.filter(parish_name__icontains=parish_name)
    if search := filters.get("search"):
        qs = qs.filter(requester_last_name__icontains=search)
    if assigned_to_id := filters.get("assigned_to_id"):
        qs = qs.filter(assigned_to_id=assigned_to_id)

    return qs.order_by("-created_at")


def document_request_get(*, request_id: UUID, user: BaseUser) -> DocumentRequest:
    qs = DocumentRequest.objects.select_related("requester", "assigned_to").prefetch_related(
        "status_logs__changed_by",
        "attachments__file",
    )
    if user.role not in _ADMIN_ROLES:
        qs = qs.filter(requester=user)

    try:
        return qs.get(pk=request_id)
    except DocumentRequest.DoesNotExist:
        raise ApplicationError(f"Demande {request_id} introuvable.")


def document_request_status_log_list(
    *, request_obj: DocumentRequest
) -> QuerySet[DocumentRequestStatusLog]:
    return (
        DocumentRequestStatusLog.objects.filter(request=request_obj)
        .select_related("changed_by")
        .order_by("created_at")
    )


def document_request_internal_note_list(*, request_obj: DocumentRequest) -> QuerySet[InternalNote]:
    return (
        InternalNote.objects.filter(request=request_obj)
        .select_related("author")
        .order_by("created_at")
    )


def document_request_attachment_list(
    *, request_obj: DocumentRequest
) -> QuerySet[DocumentRequestAttachment]:
    return (
        DocumentRequestAttachment.objects.filter(request=request_obj)
        .select_related("file", "uploaded_by")
        .order_by("created_at")
    )


def document_request_agent_recipients(*, request_obj: DocumentRequest) -> list[BaseUser]:
    """Destinataires des notifications agents pour cette demande.

    Priorité : l'agent assigné ; sinon le clergé de la paroisse cible (curé +
    vicaires) ; sinon, en repli, tous les admins actifs (comportement legacy).
    """
    if request_obj.assigned_to_id:
        return [request_obj.assigned_to]

    parish = request_obj.target_parish or getattr(
        getattr(request_obj.requester, "profile", None), "primary_parish", None
    )
    if parish is not None:
        from apps.users.scoping import clergy_of_parish

        recipients = list(clergy_of_parish(parish.id).filter(is_active=True)[:20])
        if recipients:
            return recipients

    return list(BaseUser.objects.filter(role__in=list(_ADMIN_ROLES), is_active=True)[:20])

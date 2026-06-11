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
    # target_parish__diocese : sortie B5c (nom/diocèse via la FK) sans N+1.
    qs = DocumentRequest.objects.select_related(
        "requester", "assigned_to", "target_parish__diocese"
    )

    # Source de vérité d'autorité = RoleAssignment (is_any_admin / accessible_parish_ids),
    # plus user.role seul. Fail-CLOSED : un admin sans affectation territoriale ne voit
    # RIEN (et non plus « tout », l'ancien repli legacy était un fail-open).
    from apps.users.scoping import accessible_parish_ids, is_any_admin, is_global_admin

    if not is_any_admin(user):
        qs = qs.filter(requester=user)
    elif not is_global_admin(user):
        parish_ids = accessible_parish_ids(user)  # set (jamais None ici)
        # Visibilité = admins de la paroisse CIBLE uniquement (confidentialité PII
        # inter-paroisse). Le repli sur la paroisse principale du demandeur ne vaut
        # QUE pour les demandes orphelines (target_parish NULL) — sinon le curé de la
        # paroisse home verrait une demande adressée à une AUTRE paroisse.
        qs = qs.filter(
            Q(target_parish_id__in=parish_ids)
            | Q(
                target_parish_id__isnull=True,
                requester__profile__primary_parish_id__in=parish_ids,
            )
        )
    # is_global_admin → aucune restriction

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
    from apps.users.scoping import is_any_admin

    qs = DocumentRequest.objects.select_related(
        "requester", "assigned_to", "target_parish__diocese"
    ).prefetch_related(
        "status_logs__changed_by",
        "attachments__file",
    )
    # Non-admin → ses propres demandes. Un curé (RoleAssignment, role='fidele') est
    # admin : on ne le filtre pas comme simple demandeur ; l'autorité territoriale
    # fine est tranchée par la permission objet (IsDocumentRequesterOrAdmin).
    if not is_any_admin(user):
        qs = qs.filter(requester=user)

    try:
        return qs.get(pk=request_id)
    except DocumentRequest.DoesNotExist:
        raise ApplicationError(f"Demande {request_id} introuvable.")


def _request_effective_parish_id(obj: DocumentRequest) -> Optional[int]:
    if obj.target_parish_id:
        return obj.target_parish_id
    prof = getattr(obj.requester, "profile", None)
    return getattr(prof, "primary_parish_id", None)


def document_request_get_for_admin(*, request_id: UUID, user: BaseUser) -> DocumentRequest:
    """Récupère une demande pour un agent back-office, **scopée à son autorité
    territoriale réelle** (RoleAssignment).

    Hors de la portée de l'agent → ``Http404`` (mappé en 404 par le handler ;
    pas de fuite d'existence inter-paroisses). Ferme le trou : un parish_admin
    de A ne peut plus lire/agir sur une demande de B par UUID.
    """
    from django.http import Http404

    from apps.users.scoping import accessible_parish_ids, is_global_admin

    obj = (
        DocumentRequest.objects.select_related(
            "requester", "assigned_to", "target_parish__diocese"
        )
        .prefetch_related("status_logs__changed_by", "attachments__file")
        .filter(pk=request_id)
        .first()
    )
    if obj is None:
        raise Http404

    if is_global_admin(user):
        return obj

    parish_ids = accessible_parish_ids(user)  # set (jamais None ici : global admin déjà traité)
    eff_parish_id = _request_effective_parish_id(obj)
    if parish_ids is None or eff_parish_id is None or eff_parish_id not in parish_ids:
        raise Http404
    return obj


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
    if request_obj.assigned_to is not None:
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

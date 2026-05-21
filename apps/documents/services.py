from datetime import date

from django.db import transaction

from apps.core.exceptions import ApplicationError
from apps.documents.models import (
    DocumentRequest,
    DocumentRequestAttachment,
    DocumentRequestStatusLog,
    InternalNote,
)
from apps.users.models import BaseUser

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    DocumentRequest.Status.SUBMITTED: {DocumentRequest.Status.UNDER_VERIFICATION},
    DocumentRequest.Status.UNDER_VERIFICATION: {
        DocumentRequest.Status.INFO_REQUESTED,
        DocumentRequest.Status.VALIDATED,
        DocumentRequest.Status.REJECTED,
    },
    DocumentRequest.Status.INFO_REQUESTED: {DocumentRequest.Status.UNDER_VERIFICATION},
    DocumentRequest.Status.VALIDATED: {DocumentRequest.Status.DOCUMENT_DEPOSITED},
}

_REQUIRED_DETAILS: dict[str, list[str]] = {
    DocumentRequest.DocumentType.RELIGIOUS_MARRIAGE: [
        "spouse_full_name_groom",
        "spouse_full_name_bride",
    ],
    DocumentRequest.DocumentType.GODPARENT: ["celebration_type"],
}


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------


def _generate_reference() -> str:
    import secrets

    date_str = date.today().strftime("%Y%m%d")
    suffix = secrets.token_hex(3).upper()
    return f"DOC-{date_str}-{suffix}"


def _validate_document_details(document_type: str, details: dict) -> None:
    required = _REQUIRED_DETAILS.get(document_type, [])
    missing = [f for f in required if not details.get(f)]
    if missing:
        raise ApplicationError(
            f"Champs obligatoires manquants pour {document_type} : {', '.join(missing)}"
        )


def _check_status_transition(current: str, target: str) -> None:
    allowed = _ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ApplicationError(
            f"Transition invalide : {current} → {target}. "
            f"Transitions autorisées : {', '.join(allowed) or 'aucune'}"
        )


def _log_status_change(
    *,
    request_obj: DocumentRequest,
    from_status: str,
    to_status: str,
    changed_by: BaseUser | None,
    comment: str = "",
) -> DocumentRequestStatusLog:
    return DocumentRequestStatusLog.objects.create(
        request=request_obj,
        from_status=from_status,
        to_status=to_status,
        changed_by=changed_by,
        comment=comment,
    )


def _send_email(*, to: str, subject: str, body_html: str) -> None:
    from apps.emails.models import Email
    from apps.emails.tasks import email_send as email_send_task

    email = Email.objects.create(
        to=to,
        subject=subject,
        html=body_html,
        plain_text=body_html,
        status=Email.Status.SENDING,
    )
    transaction.on_commit(lambda: email_send_task.delay(email.id))


def _notify_requester(*, request_obj: DocumentRequest, event: str, extra: str = "") -> None:
    subjects = {
        "submitted": f"[Jàngu Bi] Demande reçue — {request_obj.reference}",
        "info_requested": f"[Jàngu Bi] Complément requis — {request_obj.reference}",
        "validated": f"[Jàngu Bi] Demande validée — {request_obj.reference}",
        "rejected": f"[Jàngu Bi] Demande rejetée — {request_obj.reference}",
        "document_deposited": f"[Jàngu Bi] Document disponible — {request_obj.reference}",
    }
    bodies = {
        "submitted": (
            f"<p>Bonjour {request_obj.requester_first_names},</p>"
            f"<p>Votre demande de <strong>{request_obj.get_document_type_display()}</strong> "
            f"a été reçue avec la référence <strong>{request_obj.reference}</strong>.</p>"
            f"<p>La paroisse vous contactera pour la suite.</p>"
        ),
        "info_requested": (
            f"<p>Bonjour {request_obj.requester_first_names},</p>"
            f"<p>La paroisse a besoin d'informations complémentaires pour votre demande "
            f"<strong>{request_obj.reference}</strong>.</p><p>{extra}</p>"
        ),
        "validated": (
            f"<p>Bonjour {request_obj.requester_first_names},</p>"
            f"<p>Votre demande <strong>{request_obj.reference}</strong> a été validée. "
            f"Le document est en cours de préparation.</p>"
        ),
        "rejected": (
            f"<p>Bonjour {request_obj.requester_first_names},</p>"
            f"<p>Votre demande <strong>{request_obj.reference}</strong> a été rejetée.</p>"
            f"<p>Motif : {extra}</p>"
        ),
        "document_deposited": (
            f"<p>Bonjour {request_obj.requester_first_names},</p>"
            f"<p>Votre document pour la demande <strong>{request_obj.reference}</strong> "
            f"est disponible dans votre espace personnel.</p>"
        ),
    }
    _send_email(to=request_obj.contact_email, subject=subjects[event], body_html=bodies[event])


def _notify_agents(*, request_obj: DocumentRequest, event: str) -> None:
    subjects = {
        "submitted": f"[Jàngu Bi] Nouvelle demande — {request_obj.reference}",
        "supplement_received": f"[Jàngu Bi] Complément reçu — {request_obj.reference}",
        "document_deposited": f"[Jàngu Bi] Dépôt confirmé — {request_obj.reference}",
    }
    bodies = {
        "submitted": (
            f"<p>Nouvelle demande de <strong>{request_obj.get_document_type_display()}</strong>.</p>"
            f"<p>Référence : <strong>{request_obj.reference}</strong><br>"
            f"Demandeur : {request_obj.requester_last_name} {request_obj.requester_first_names}<br>"
            f"Paroisse : {request_obj.parish_name}</p>"
        ),
        "supplement_received": (
            f"<p>Le demandeur a fourni un complément d'informations pour la demande "
            f"<strong>{request_obj.reference}</strong>.</p>"
        ),
        "document_deposited": (
            f"<p>Le document pour la demande <strong>{request_obj.reference}</strong> "
            f"a été déposé avec succès.</p>"
        ),
    }
    if event not in subjects:
        return
    from apps.documents.selectors import document_request_agent_recipients

    for agent in document_request_agent_recipients(request_obj=request_obj):
        _send_email(to=agent.email, subject=subjects[event], body_html=bodies[event])


def _attach_file(
    *,
    request_obj: DocumentRequest,
    file_id: int,
    uploaded_by: BaseUser | None,
    attachment_type: str,
    label: str = "",
) -> DocumentRequestAttachment:
    from apps.files.models import File

    try:
        file_obj = File.objects.get(pk=file_id)
    except File.DoesNotExist:
        raise ApplicationError(f"Fichier {file_id} introuvable.")
    if not file_obj.is_valid:
        raise ApplicationError("Le fichier n'a pas encore été finalisé (upload incomplet).")

    return DocumentRequestAttachment.objects.create(
        request=request_obj,
        file=file_obj,
        uploaded_by=uploaded_by,
        attachment_type=attachment_type,
        label=label,
    )


# ---------------------------------------------------------------------------
# Services publics
# ---------------------------------------------------------------------------


@transaction.atomic
def document_request_create(*, requester: BaseUser, data: dict) -> DocumentRequest:
    document_type = data["document_type"]
    document_details = data.get("document_details", {})
    _validate_document_details(document_type, document_details)

    attachment_file_id = data.get("attachment_file_id")

    request_obj = DocumentRequest.objects.create(
        reference=_generate_reference(),
        requester=requester,
        document_type=document_type,
        reason=data["reason"],
        reason_free=data.get("reason_free", ""),
        requester_last_name=data["requester_last_name"],
        requester_first_names=data["requester_first_names"],
        date_of_birth=data["date_of_birth"],
        place_of_birth=data["place_of_birth"],
        contact_phone=data["contact_phone"],
        contact_email=data["contact_email"],
        registered_last_name=data.get("registered_last_name", ""),
        registered_first_names=data.get("registered_first_names", ""),
        father_last_name=data["father_last_name"],
        mother_last_name=data["mother_last_name"],
        parish_name=data["parish_name"],
        diocese=data["diocese"],
        sacrament_approximate_date=data["sacrament_approximate_date"],
        sacrament_location=data["sacrament_location"],
        additional_info=data.get("additional_info", ""),
        document_details=document_details,
        consent_given=data["consent_given"],
        status=DocumentRequest.Status.SUBMITTED,
    )

    _log_status_change(
        request_obj=request_obj,
        from_status="",
        to_status=DocumentRequest.Status.SUBMITTED,
        changed_by=requester,
    )

    if attachment_file_id:
        _attach_file(
            request_obj=request_obj,
            file_id=attachment_file_id,
            uploaded_by=requester,
            attachment_type=DocumentRequest.AttachmentType.USER_SUPPORTING,
        )

    transaction.on_commit(lambda: _notify_requester(request_obj=request_obj, event="submitted"))
    transaction.on_commit(lambda: _notify_agents(request_obj=request_obj, event="submitted"))

    return request_obj


@transaction.atomic
def document_request_submit_supplement(
    *, request_obj: DocumentRequest, requester: BaseUser, data: dict
) -> DocumentRequest:
    if request_obj.requester_id != requester.id:
        raise ApplicationError("Vous ne pouvez modifier que vos propres demandes.")
    _check_status_transition(request_obj.status, DocumentRequest.Status.UNDER_VERIFICATION)

    if additional_info := data.get("additional_info"):
        request_obj.additional_info = additional_info
    if document_details := data.get("document_details"):
        request_obj.document_details = {**request_obj.document_details, **document_details}

    prev_status = request_obj.status
    request_obj.status = DocumentRequest.Status.UNDER_VERIFICATION
    request_obj.save(update_fields=["status", "additional_info", "document_details", "updated_at"])

    _log_status_change(
        request_obj=request_obj,
        from_status=prev_status,
        to_status=DocumentRequest.Status.UNDER_VERIFICATION,
        changed_by=requester,
        comment="Complément fourni par le demandeur.",
    )

    transaction.on_commit(
        lambda: _notify_agents(request_obj=request_obj, event="supplement_received")
    )
    return request_obj


@transaction.atomic
def document_request_start_verification(
    *, request_obj: DocumentRequest, agent: BaseUser
) -> DocumentRequest:
    _check_status_transition(request_obj.status, DocumentRequest.Status.UNDER_VERIFICATION)

    prev_status = request_obj.status
    request_obj.status = DocumentRequest.Status.UNDER_VERIFICATION
    request_obj.assigned_to = agent
    request_obj.save(update_fields=["status", "assigned_to", "updated_at"])

    _log_status_change(
        request_obj=request_obj,
        from_status=prev_status,
        to_status=DocumentRequest.Status.UNDER_VERIFICATION,
        changed_by=agent,
    )
    return request_obj


@transaction.atomic
def document_request_request_info(
    *, request_obj: DocumentRequest, agent: BaseUser, comment: str
) -> DocumentRequest:
    _check_status_transition(request_obj.status, DocumentRequest.Status.INFO_REQUESTED)

    prev_status = request_obj.status
    request_obj.status = DocumentRequest.Status.INFO_REQUESTED
    request_obj.save(update_fields=["status", "updated_at"])

    _log_status_change(
        request_obj=request_obj,
        from_status=prev_status,
        to_status=DocumentRequest.Status.INFO_REQUESTED,
        changed_by=agent,
        comment=comment,
    )

    transaction.on_commit(
        lambda: _notify_requester(request_obj=request_obj, event="info_requested", extra=comment)
    )
    return request_obj


@transaction.atomic
def document_request_validate(
    *, request_obj: DocumentRequest, agent: BaseUser
) -> DocumentRequest:
    _check_status_transition(request_obj.status, DocumentRequest.Status.VALIDATED)

    prev_status = request_obj.status
    request_obj.status = DocumentRequest.Status.VALIDATED
    request_obj.save(update_fields=["status", "updated_at"])

    _log_status_change(
        request_obj=request_obj,
        from_status=prev_status,
        to_status=DocumentRequest.Status.VALIDATED,
        changed_by=agent,
    )

    transaction.on_commit(lambda: _notify_requester(request_obj=request_obj, event="validated"))
    return request_obj


@transaction.atomic
def document_request_reject(
    *, request_obj: DocumentRequest, agent: BaseUser, reason: str
) -> DocumentRequest:
    if not reason.strip():
        raise ApplicationError("Le motif de rejet est obligatoire.")
    _check_status_transition(request_obj.status, DocumentRequest.Status.REJECTED)

    prev_status = request_obj.status
    request_obj.status = DocumentRequest.Status.REJECTED
    request_obj.rejection_reason = reason
    request_obj.save(update_fields=["status", "rejection_reason", "updated_at"])

    _log_status_change(
        request_obj=request_obj,
        from_status=prev_status,
        to_status=DocumentRequest.Status.REJECTED,
        changed_by=agent,
        comment=reason,
    )

    transaction.on_commit(
        lambda: _notify_requester(request_obj=request_obj, event="rejected", extra=reason)
    )
    return request_obj


@transaction.atomic
def document_request_deposit_document(
    *,
    request_obj: DocumentRequest,
    agent: BaseUser,
    file_id: int,
    label: str = "Document officiel",
) -> DocumentRequest:
    _check_status_transition(request_obj.status, DocumentRequest.Status.DOCUMENT_DEPOSITED)

    _attach_file(
        request_obj=request_obj,
        file_id=file_id,
        uploaded_by=agent,
        attachment_type=DocumentRequest.AttachmentType.PARISH_FINAL,
        label=label,
    )

    prev_status = request_obj.status
    request_obj.status = DocumentRequest.Status.DOCUMENT_DEPOSITED
    request_obj.save(update_fields=["status", "updated_at"])

    _log_status_change(
        request_obj=request_obj,
        from_status=prev_status,
        to_status=DocumentRequest.Status.DOCUMENT_DEPOSITED,
        changed_by=agent,
    )

    transaction.on_commit(
        lambda: _notify_requester(request_obj=request_obj, event="document_deposited")
    )
    transaction.on_commit(
        lambda: _notify_agents(request_obj=request_obj, event="document_deposited")
    )
    return request_obj


@transaction.atomic
def document_request_add_internal_note(
    *, request_obj: DocumentRequest, author: BaseUser, content: str
) -> InternalNote:
    return InternalNote.objects.create(
        request=request_obj,
        author=author,
        content=content,
    )


@transaction.atomic
def document_request_run_escalation(
    *,
    escalate_days: int,
    deposit_reminder_days: int,
    requester_reminder_days: int,
) -> None:
    """Send reminder emails for stale document requests. Called from the Celery Beat task."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.documents.selectors import document_request_agent_recipients

    now = timezone.now()

    for req in DocumentRequest.objects.filter(
        status=DocumentRequest.Status.SUBMITTED,
        updated_at__lt=now - timedelta(days=escalate_days),
    ).select_related("assigned_to", "requester"):
        _send_email(
            to=req.contact_email,
            subject=f"[Jàngu Bi] Votre demande {req.reference} est en attente",
            body_html=(
                f"<p>Bonjour {req.requester_first_names},</p>"
                f"<p>Votre demande <strong>{req.reference}</strong> est en attente de traitement "
                f"depuis plus de {escalate_days} jours.</p>"
            ),
        )
        for agent in document_request_agent_recipients(request_obj=req):
            _send_email(
                to=agent.email,
                subject=f"[Jàngu Bi] Demande en attente — {req.reference}",
                body_html=(
                    f"<p>La demande <strong>{req.reference}</strong> est soumise depuis plus de "
                    f"{escalate_days} jours sans prise en charge.</p>"
                ),
            )

    for req in DocumentRequest.objects.filter(
        status=DocumentRequest.Status.UNDER_VERIFICATION,
        updated_at__lt=now - timedelta(days=escalate_days),
    ).select_related("assigned_to"):
        for agent in document_request_agent_recipients(request_obj=req):
            _send_email(
                to=agent.email,
                subject=f"[Jàngu Bi] Vérification en attente — {req.reference}",
                body_html=(
                    f"<p>La demande <strong>{req.reference}</strong> est en vérification depuis "
                    f"plus de {escalate_days} jours.</p>"
                ),
            )

    for req in DocumentRequest.objects.filter(
        status=DocumentRequest.Status.VALIDATED,
        updated_at__lt=now - timedelta(days=deposit_reminder_days),
    ).select_related("assigned_to"):
        for agent in document_request_agent_recipients(request_obj=req):
            _send_email(
                to=agent.email,
                subject=f"[Jàngu Bi] Rappel dépôt — {req.reference}",
                body_html=(
                    f"<p>La demande <strong>{req.reference}</strong> est validée depuis plus de "
                    f"{deposit_reminder_days} jours. Merci de déposer le document final.</p>"
                ),
            )

    for req in DocumentRequest.objects.filter(
        status=DocumentRequest.Status.INFO_REQUESTED,
        updated_at__lt=now - timedelta(days=requester_reminder_days),
    ).select_related("requester"):
        _send_email(
            to=req.contact_email,
            subject=f"[Jàngu Bi] Rappel complément — {req.reference}",
            body_html=(
                f"<p>Bonjour {req.requester_first_names},</p>"
                f"<p>Nous attendons toujours votre complément pour la demande "
                f"<strong>{req.reference}</strong>. Merci de répondre dans les meilleurs délais.</p>"
            ),
        )

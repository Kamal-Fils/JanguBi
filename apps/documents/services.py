from datetime import date

from django.db import transaction

from apps.core.exceptions import ApplicationError
from apps.documents.constants import allowed_reasons_for, is_reason_allowed
from apps.documents.models import (
    DocumentRequest,
    DocumentRequestAttachment,
    DocumentRequestStatusLog,
    InternalNote,
)
from apps.users.enums import PastoralRole
from apps.users.models import BaseUser

# Hiérarchie pastorale de signature (permissions-matrix.md — §Documents).
# La validation (Niv.2) ET le dépôt du document final sont des actes de SIGNATURE
# réservés au clergé prêtre et au-dessus. Un diacre ou un administrateur digital
# non-clergé (pastoral_role absent, ex. un parish_admin laïc) NE PEUT PAS signer,
# même s'il franchit le gate view-level IsAnyAdmin et l'autorité territoriale.
_SIGNATORY_ROLES = {
    PastoralRole.PRETRE,
    PastoralRole.EVEQUE,
    PastoralRole.ARCHEVEQUE,
}

# Niv.3 — autorité épiscopale. Documents diocésains réservés à l'évêque et au-dessus.
_BISHOP_ROLES = {
    PastoralRole.EVEQUE,
    PastoralRole.ARCHEVEQUE,
}

# Types de documents diocésains / épiscopaux (Niv.3 — SRS « ordinations_cert »).
# La confirmation est le sacrement conféré par l'évêque : son attestation relève de
# l'autorité épiscopale. Les certificats d'ordination rejoindront ce set dès que le
# type de document existera dans le modèle.
_DIOCESAN_DOCUMENT_TYPES = {
    DocumentRequest.DocumentType.CONFIRMATION,
}

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


def _validate_free_text_precisions(
    *, document_type: str, document_type_free: str, reason: str, reason_free: str
) -> None:
    """« Autre » n'est un choix valide qu'accompagné de sa précision libre.

    Sans cette garde, une demande « Autre document / Autre motif » arriverait à la
    paroisse sans dire de quoi il s'agit — donc impossible à traiter.
    """
    if document_type == DocumentRequest.DocumentType.OTHER and not document_type_free.strip():
        raise ApplicationError(
            "Veuillez préciser le document demandé lorsque vous choisissez « Autre document »."
        )
    if reason == DocumentRequest.RequestReason.OTHER and not reason_free.strip():
        raise ApplicationError(
            "Veuillez préciser le motif de votre demande lorsque vous choisissez « Autre »."
        )


def _validate_reason_matches_document_type(*, document_type: str, reason: str) -> None:
    """Cohérence pastorale type ↔ motif (apps.documents.constants).

    Contrôle SERVEUR : le filtrage du formulaire n'est qu'un confort d'usage et
    reste contournable (appel direct à l'API).
    """
    if is_reason_allowed(document_type=document_type, reason=reason):
        return

    labels = dict(DocumentRequest.RequestReason.choices)
    permitted = ", ".join(
        str(labels[value]) for value in allowed_reasons_for(document_type) if value in labels
    )
    raise ApplicationError(
        f"Le motif « {labels.get(reason, reason)} » ne correspond pas au document demandé. "
        f"Motifs possibles : {permitted}."
    )


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


def _check_signing_authority(*, agent: BaseUser, document_type: str) -> None:
    """Garde pastorale des actes de signature (validate / deposit).

    La signature d'une demande est un acte pastoral réservé au clergé : prêtre et
    au-dessus pour les documents courants, évêque et au-dessus pour les documents
    diocésains. Lève ``ApplicationError`` (→ HTTP 400) pour tout autre acteur, y
    compris un diacre, un administrateur digital non-clergé ou un super-admin
    (``pastoral_role`` absent).
    """
    role = getattr(agent, "pastoral_role", None)
    if document_type in _DIOCESAN_DOCUMENT_TYPES:
        if role not in _BISHOP_ROLES:
            raise ApplicationError(
                "Acte réservé à l'autorité épiscopale : ce document diocésain ne peut "
                "être signé que par un évêque ou un archevêque."
            )
        return
    if role not in _SIGNATORY_ROLES:
        raise ApplicationError(
            "Acte de signature réservé au clergé : seul un prêtre (ou un rang "
            "supérieur) peut valider et déposer une demande de document."
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
    document_type_free = data.get("document_type_free", "") or ""
    reason = data["reason"]
    reason_free = data.get("reason_free", "") or ""
    document_details = data.get("document_details", {})

    _validate_free_text_precisions(
        document_type=document_type,
        document_type_free=document_type_free,
        reason=reason,
        reason_free=reason_free,
    )
    _validate_reason_matches_document_type(document_type=document_type, reason=reason)
    _validate_document_details(document_type, document_details)

    attachment_file_id = data.get("attachment_file_id")

    # Rattachement territorial. La paroisse du REGISTRE peut être N'IMPORTE QUELLE
    # paroisse active (Chantier 4) : un fidèle demande un document À une paroisse sans
    # y être membre ni admin → AUCUN contrôle d'autorité côté demandeur.
    # B5c — parish_id est REQUIS (le front l'émet via le picker). A5 préservé : parish_id
    # absent ou invalide → erreur (jamais de repli silencieux ni de demande orpheline).
    parish_id = data.get("parish_id")
    if not parish_id:
        raise ApplicationError("La paroisse du registre est requise (parish_id).")

    from apps.org.models import Parish

    target_parish = Parish.objects.filter(id=parish_id).select_related("diocese").first()
    if target_parish is None:
        raise ApplicationError("Paroisse cible introuvable.")

    # Nom de paroisse + diocèse DÉRIVÉS du FK (plus de texte libre en entrée). Les
    # anciennes demandes orphelines (FK NULL) conservent leur parish_name/diocese stockés.
    parish_name_value = target_parish.name
    diocese_value = target_parish.diocese.name

    request_obj = DocumentRequest.objects.create(
        reference=_generate_reference(),
        requester=requester,
        document_type=document_type,
        # Les précisions ne sont conservées que si « Autre » est bien le choix
        # retenu : un texte laissé par un aller-retour du formulaire ne doit pas
        # se retrouver stocké à côté d'un type/motif normalisé qui le contredit.
        document_type_free=(
            document_type_free.strip()
            if document_type == DocumentRequest.DocumentType.OTHER
            else ""
        ),
        reason=reason,
        reason_free=(
            reason_free.strip() if reason == DocumentRequest.RequestReason.OTHER else ""
        ),
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
        parish_name=parish_name_value,
        diocese=diocese_value,
        target_parish=target_parish,
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
    _check_signing_authority(agent=agent, document_type=request_obj.document_type)
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
    _check_signing_authority(agent=agent, document_type=request_obj.document_type)
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

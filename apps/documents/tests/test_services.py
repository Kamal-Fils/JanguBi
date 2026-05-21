"""
Tests des services documents — HackSoft Styleguide.
Pattern AAA (Arrange / Act / Assert) sur chaque test.
Les appels email sont supprimés en patchant transaction.on_commit.
"""

import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.core.exceptions import ApplicationError
from apps.documents.models import DocumentRequest, DocumentRequestStatusLog, InternalNote
from apps.documents.services import (
    _generate_reference,
    document_request_add_internal_note,
    document_request_create,
    document_request_deposit_document,
    document_request_reject,
    document_request_request_info,
    document_request_run_escalation,
    document_request_start_verification,
    document_request_submit_supplement,
    document_request_validate,
)
from apps.users.tests.factories import BaseUserFactory, StaffUserFactory

from .factories import (
    DocumentRequestFactory,
    InvalidFileFactory,
    ValidFileFactory,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MINIMUM_DATA = {
    "document_type": DocumentRequest.DocumentType.BAPTISM,
    "reason": DocumentRequest.RequestReason.PERSONAL,
    "requester_last_name": "Diallo",
    "requester_first_names": "Aminata",
    "date_of_birth": "1990-01-01",
    "place_of_birth": "Dakar",
    "contact_phone": "+221771234567",
    "contact_email": "aminata@example.com",
    "father_last_name": "Moussa",
    "mother_last_name": "Ndiaye",
    "parish_name": "Saint-Pierre",
    "diocese": "Dakar",
    "sacrament_approximate_date": "2005",
    "sacrament_location": "Dakar",
    "consent_given": True,
}


# ---------------------------------------------------------------------------
# document_request_create
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_document_request_create_success():
    # Arrange
    requester = BaseUserFactory()
    data = {**MINIMUM_DATA}

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        result = document_request_create(requester=requester, data=data)

    # Assert
    assert result.id is not None
    assert result.requester == requester
    assert result.status == DocumentRequest.Status.SUBMITTED
    assert result.reference.startswith("DOC-")
    assert result.document_type == DocumentRequest.DocumentType.BAPTISM
    assert result.consent_given is True


@pytest.mark.django_db
def test_document_request_create_logs_initial_status():
    # Arrange
    requester = BaseUserFactory()
    data = {**MINIMUM_DATA}

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        result = document_request_create(requester=requester, data=data)

    # Assert
    log = DocumentRequestStatusLog.objects.get(request=result)
    assert log.from_status == ""
    assert log.to_status == DocumentRequest.Status.SUBMITTED
    assert log.changed_by == requester


@pytest.mark.django_db
def test_document_request_create_with_valid_attachment():
    # Arrange
    requester = BaseUserFactory()
    valid_file = ValidFileFactory(uploaded_by=requester)
    data = {**MINIMUM_DATA, "attachment_file_id": valid_file.id}

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        result = document_request_create(requester=requester, data=data)

    # Assert
    assert result.attachments.count() == 1
    assert result.attachments.first().file == valid_file


@pytest.mark.django_db
def test_document_request_create_raises_when_attachment_not_found():
    # Arrange
    requester = BaseUserFactory()
    data = {**MINIMUM_DATA, "attachment_file_id": uuid.uuid4()}

    # Act & Assert
    with patch("apps.documents.services.transaction.on_commit"):
        with pytest.raises(ApplicationError, match="introuvable"):
            document_request_create(requester=requester, data=data)


@pytest.mark.django_db
def test_document_request_create_raises_when_attachment_not_finalized():
    # Arrange
    requester = BaseUserFactory()
    invalid_file = InvalidFileFactory(uploaded_by=requester)
    data = {**MINIMUM_DATA, "attachment_file_id": invalid_file.id}

    # Act & Assert
    with patch("apps.documents.services.transaction.on_commit"):
        with pytest.raises(ApplicationError, match="upload incomplet"):
            document_request_create(requester=requester, data=data)


@pytest.mark.django_db
def test_document_request_create_raises_when_religious_marriage_missing_details():
    # Arrange
    requester = BaseUserFactory()
    data = {
        **MINIMUM_DATA,
        "document_type": DocumentRequest.DocumentType.RELIGIOUS_MARRIAGE,
        "document_details": {},
    }

    # Act & Assert
    with patch("apps.documents.services.transaction.on_commit"):
        with pytest.raises(ApplicationError, match="Champs obligatoires manquants"):
            document_request_create(requester=requester, data=data)


@pytest.mark.django_db
def test_document_request_create_raises_when_godparent_missing_celebration_type():
    # Arrange
    requester = BaseUserFactory()
    data = {
        **MINIMUM_DATA,
        "document_type": DocumentRequest.DocumentType.GODPARENT,
        "document_details": {},
    }

    # Act & Assert
    with patch("apps.documents.services.transaction.on_commit"):
        with pytest.raises(ApplicationError, match="Champs obligatoires manquants"):
            document_request_create(requester=requester, data=data)


@pytest.mark.django_db
def test_document_request_create_succeeds_with_valid_religious_marriage_details():
    # Arrange
    requester = BaseUserFactory()
    data = {
        **MINIMUM_DATA,
        "document_type": DocumentRequest.DocumentType.RELIGIOUS_MARRIAGE,
        "document_details": {
            "spouse_full_name_groom": "Jean Dupont",
            "spouse_full_name_bride": "Marie Ndiaye",
        },
    }

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        result = document_request_create(requester=requester, data=data)

    # Assert
    assert result.status == DocumentRequest.Status.SUBMITTED
    assert result.document_details["spouse_full_name_groom"] == "Jean Dupont"


# ---------------------------------------------------------------------------
# document_request_start_verification
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_document_request_start_verification_success():
    # Arrange
    agent = StaffUserFactory()
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.SUBMITTED)

    # Act
    result = document_request_start_verification(request_obj=doc_request, agent=agent)

    # Assert
    assert result.status == DocumentRequest.Status.UNDER_VERIFICATION
    assert result.assigned_to == agent


@pytest.mark.django_db
def test_document_request_start_verification_creates_log():
    # Arrange
    agent = StaffUserFactory()
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.SUBMITTED)

    # Act
    document_request_start_verification(request_obj=doc_request, agent=agent)

    # Assert
    log = DocumentRequestStatusLog.objects.filter(
        request=doc_request,
        to_status=DocumentRequest.Status.UNDER_VERIFICATION,
    ).last()
    assert log is not None
    assert log.changed_by == agent


@pytest.mark.django_db
def test_document_request_start_verification_raises_on_invalid_transition():
    # Arrange
    agent = StaffUserFactory()
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.VALIDATED)

    # Act & Assert
    with pytest.raises(ApplicationError, match="Transition invalide"):
        document_request_start_verification(request_obj=doc_request, agent=agent)


# ---------------------------------------------------------------------------
# document_request_request_info
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_document_request_request_info_success():
    # Arrange
    agent = StaffUserFactory()
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.UNDER_VERIFICATION)

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        result = document_request_request_info(
            request_obj=doc_request,
            agent=agent,
            comment="Merci de fournir votre acte de naissance.",
        )

    # Assert
    assert result.status == DocumentRequest.Status.INFO_REQUESTED


@pytest.mark.django_db
def test_document_request_request_info_stores_comment_in_log():
    # Arrange
    agent = StaffUserFactory()
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.UNDER_VERIFICATION)
    comment = "Acte de naissance requis."

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        document_request_request_info(request_obj=doc_request, agent=agent, comment=comment)

    # Assert
    log = DocumentRequestStatusLog.objects.filter(
        request=doc_request, to_status=DocumentRequest.Status.INFO_REQUESTED
    ).last()
    assert log is not None
    assert log.comment == comment


@pytest.mark.django_db
def test_document_request_request_info_raises_on_invalid_transition():
    # Arrange
    agent = StaffUserFactory()
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.SUBMITTED)

    # Act & Assert
    with patch("apps.documents.services.transaction.on_commit"):
        with pytest.raises(ApplicationError, match="Transition invalide"):
            document_request_request_info(
                request_obj=doc_request, agent=agent, comment="commentaire"
            )


# ---------------------------------------------------------------------------
# document_request_submit_supplement
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_document_request_submit_supplement_success():
    # Arrange
    requester = BaseUserFactory()
    doc_request = DocumentRequestFactory(
        requester=requester, status=DocumentRequest.Status.INFO_REQUESTED
    )

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        result = document_request_submit_supplement(
            request_obj=doc_request,
            requester=requester,
            data={"additional_info": "Voici les informations demandées."},
        )

    # Assert
    assert result.status == DocumentRequest.Status.UNDER_VERIFICATION
    assert result.additional_info == "Voici les informations demandées."


@pytest.mark.django_db
def test_document_request_submit_supplement_merges_document_details():
    # Arrange
    requester = BaseUserFactory()
    doc_request = DocumentRequestFactory(
        requester=requester,
        status=DocumentRequest.Status.INFO_REQUESTED,
        document_details={"existing_key": "existing_value"},
    )

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        result = document_request_submit_supplement(
            request_obj=doc_request,
            requester=requester,
            data={"document_details": {"new_key": "new_value"}},
        )

    # Assert
    assert result.document_details["existing_key"] == "existing_value"
    assert result.document_details["new_key"] == "new_value"


@pytest.mark.django_db
def test_document_request_submit_supplement_raises_when_not_owner():
    # Arrange
    requester = BaseUserFactory()
    other_user = BaseUserFactory()
    doc_request = DocumentRequestFactory(
        requester=requester, status=DocumentRequest.Status.INFO_REQUESTED
    )

    # Act & Assert
    with patch("apps.documents.services.transaction.on_commit"):
        with pytest.raises(ApplicationError, match="propres demandes"):
            document_request_submit_supplement(
                request_obj=doc_request,
                requester=other_user,
                data={"additional_info": "info"},
            )


@pytest.mark.django_db
def test_document_request_submit_supplement_raises_on_invalid_transition():
    # Arrange
    requester = BaseUserFactory()
    doc_request = DocumentRequestFactory(
        requester=requester, status=DocumentRequest.Status.VALIDATED
    )

    # Act & Assert
    with patch("apps.documents.services.transaction.on_commit"):
        with pytest.raises(ApplicationError, match="Transition invalide"):
            document_request_submit_supplement(
                request_obj=doc_request,
                requester=requester,
                data={"additional_info": "info"},
            )


# ---------------------------------------------------------------------------
# document_request_validate
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_document_request_validate_success():
    # Arrange
    agent = StaffUserFactory()
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.UNDER_VERIFICATION)

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        result = document_request_validate(request_obj=doc_request, agent=agent)

    # Assert
    assert result.status == DocumentRequest.Status.VALIDATED


@pytest.mark.django_db
def test_document_request_validate_creates_log():
    # Arrange
    agent = StaffUserFactory()
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.UNDER_VERIFICATION)

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        document_request_validate(request_obj=doc_request, agent=agent)

    # Assert
    log = DocumentRequestStatusLog.objects.filter(
        request=doc_request, to_status=DocumentRequest.Status.VALIDATED
    ).last()
    assert log is not None
    assert log.changed_by == agent


@pytest.mark.django_db
def test_document_request_validate_raises_on_invalid_transition():
    # Arrange
    agent = StaffUserFactory()
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.SUBMITTED)

    # Act & Assert
    with patch("apps.documents.services.transaction.on_commit"):
        with pytest.raises(ApplicationError, match="Transition invalide"):
            document_request_validate(request_obj=doc_request, agent=agent)


# ---------------------------------------------------------------------------
# document_request_reject
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_document_request_reject_success():
    # Arrange
    agent = StaffUserFactory()
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.UNDER_VERIFICATION)

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        result = document_request_reject(
            request_obj=doc_request,
            agent=agent,
            reason="Document introuvable dans les archives.",
        )

    # Assert
    assert result.status == DocumentRequest.Status.REJECTED
    assert result.rejection_reason == "Document introuvable dans les archives."


@pytest.mark.django_db
def test_document_request_reject_raises_when_reason_blank():
    # Arrange
    agent = StaffUserFactory()
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.UNDER_VERIFICATION)

    # Act & Assert
    with patch("apps.documents.services.transaction.on_commit"):
        with pytest.raises(ApplicationError, match="motif de rejet est obligatoire"):
            document_request_reject(request_obj=doc_request, agent=agent, reason="   ")


@pytest.mark.django_db
def test_document_request_reject_raises_on_invalid_transition():
    # Arrange
    agent = StaffUserFactory()
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.VALIDATED)

    # Act & Assert
    with patch("apps.documents.services.transaction.on_commit"):
        with pytest.raises(ApplicationError, match="Transition invalide"):
            document_request_reject(
                request_obj=doc_request, agent=agent, reason="Motif valide"
            )


# ---------------------------------------------------------------------------
# document_request_deposit_document
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_document_request_deposit_document_success():
    # Arrange
    agent = StaffUserFactory()
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.VALIDATED)
    valid_file = ValidFileFactory(uploaded_by=agent)

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        result = document_request_deposit_document(
            request_obj=doc_request,
            agent=agent,
            file_id=valid_file.id,
            label="Certificat de baptême",
        )

    # Assert
    assert result.status == DocumentRequest.Status.DOCUMENT_DEPOSITED
    assert result.attachments.count() == 1
    attachment = result.attachments.first()
    assert attachment.attachment_type == DocumentRequest.AttachmentType.PARISH_FINAL
    assert attachment.label == "Certificat de baptême"


@pytest.mark.django_db
def test_document_request_deposit_document_raises_on_invalid_transition():
    # Arrange
    agent = StaffUserFactory()
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.SUBMITTED)
    valid_file = ValidFileFactory(uploaded_by=agent)

    # Act & Assert
    with patch("apps.documents.services.transaction.on_commit"):
        with pytest.raises(ApplicationError, match="Transition invalide"):
            document_request_deposit_document(
                request_obj=doc_request, agent=agent, file_id=valid_file.id
            )


@pytest.mark.django_db
def test_document_request_deposit_document_raises_when_file_not_finalized():
    # Arrange
    agent = StaffUserFactory()
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.VALIDATED)
    invalid_file = InvalidFileFactory(uploaded_by=agent)

    # Act & Assert
    with patch("apps.documents.services.transaction.on_commit"):
        with pytest.raises(ApplicationError, match="upload incomplet"):
            document_request_deposit_document(
                request_obj=doc_request, agent=agent, file_id=invalid_file.id
            )


@pytest.mark.django_db
def test_document_request_deposit_document_raises_when_file_not_found():
    # Arrange
    agent = StaffUserFactory()
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.VALIDATED)

    # Act & Assert
    with patch("apps.documents.services.transaction.on_commit"):
        with pytest.raises(ApplicationError, match="introuvable"):
            document_request_deposit_document(
                request_obj=doc_request, agent=agent, file_id=uuid.uuid4()
            )


# ---------------------------------------------------------------------------
# document_request_add_internal_note
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_document_request_add_internal_note_success():
    # Arrange
    agent = StaffUserFactory()
    doc_request = DocumentRequestFactory()

    # Act
    note = document_request_add_internal_note(
        request_obj=doc_request,
        author=agent,
        content="Vérification en cours avec le registre paroissial.",
    )

    # Assert
    assert note.id is not None
    assert note.request == doc_request
    assert note.author == agent
    assert note.content == "Vérification en cours avec le registre paroissial."
    assert InternalNote.objects.filter(request=doc_request).count() == 1


@pytest.mark.django_db
def test_document_request_add_multiple_internal_notes():
    # Arrange
    agent = StaffUserFactory()
    doc_request = DocumentRequestFactory()

    # Act
    document_request_add_internal_note(
        request_obj=doc_request, author=agent, content="Première note."
    )
    document_request_add_internal_note(
        request_obj=doc_request, author=agent, content="Deuxième note."
    )

    # Assert
    assert InternalNote.objects.filter(request=doc_request).count() == 2


# ---------------------------------------------------------------------------
# _generate_reference
# ---------------------------------------------------------------------------


def test_generate_reference_matches_expected_format():
    # Act
    ref = _generate_reference()

    # Assert — format: DOC-YYYYMMDD-XXXXXX
    parts = ref.split("-")
    assert parts[0] == "DOC"
    assert len(parts[1]) == 8  # YYYYMMDD
    assert parts[1].isdigit()
    assert len(parts[2]) == 6  # hex suffix (3 bytes = 6 hex chars)
    assert parts[2] == parts[2].upper()


def test_generate_reference_produces_unique_values():
    # Act — generate 50 references in rapid succession
    references = [_generate_reference() for _ in range(50)]

    # Assert — no duplicates due to secrets.token_hex randomness
    assert len(references) == len(set(references))


# ---------------------------------------------------------------------------
# document_request_run_escalation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_escalation_sends_email_for_stale_submitted_requests():
    # Arrange — request submitted long ago (> escalate_days)
    past = timezone.now() - timedelta(days=10)
    req = DocumentRequestFactory(status=DocumentRequest.Status.SUBMITTED)
    DocumentRequest.objects.filter(id=req.id).update(updated_at=past)

    # Act
    with patch("apps.documents.services._send_email") as mock_send:
        document_request_run_escalation(
            escalate_days=7,
            deposit_reminder_days=3,
            requester_reminder_days=5,
        )

    # Assert — at least one email sent to the requester
    assert mock_send.called
    sent_tos = [call.kwargs["to"] for call in mock_send.call_args_list]
    assert req.contact_email in sent_tos


@pytest.mark.django_db
def test_escalation_does_not_send_email_for_recent_submitted_requests():
    # Arrange — request just submitted (< escalate_days)
    DocumentRequestFactory(status=DocumentRequest.Status.SUBMITTED)

    # Act
    with patch("apps.documents.services._send_email") as mock_send:
        document_request_run_escalation(
            escalate_days=7,
            deposit_reminder_days=3,
            requester_reminder_days=5,
        )

    # Assert — no emails sent
    assert not mock_send.called


@pytest.mark.django_db
def test_escalation_sends_email_for_stale_under_verification_requests():
    # Arrange — request under verification for too long; assigned so agent gets email
    agent = StaffUserFactory()
    past = timezone.now() - timedelta(days=10)
    req = DocumentRequestFactory(status=DocumentRequest.Status.UNDER_VERIFICATION, assigned_to=agent)
    DocumentRequest.objects.filter(id=req.id).update(updated_at=past)
    req.refresh_from_db()

    # Act
    with patch("apps.documents.services._send_email") as mock_send:
        document_request_run_escalation(
            escalate_days=7,
            deposit_reminder_days=3,
            requester_reminder_days=5,
        )

    # Assert — email triggered (may go to agents if any are assigned)
    mock_send.assert_called()


@pytest.mark.django_db
def test_escalation_sends_deposit_reminder_for_stale_validated_requests():
    # Arrange — request validated but not deposited; assigned so agent gets email
    agent = StaffUserFactory()
    past = timezone.now() - timedelta(days=5)
    req = DocumentRequestFactory(status=DocumentRequest.Status.VALIDATED, assigned_to=agent)
    DocumentRequest.objects.filter(id=req.id).update(updated_at=past)

    # Act
    with patch("apps.documents.services._send_email") as mock_send:
        document_request_run_escalation(
            escalate_days=7,
            deposit_reminder_days=3,
            requester_reminder_days=5,
        )

    # Assert — deposit reminder triggered (goes to agents if any)
    mock_send.assert_called()


@pytest.mark.django_db
def test_escalation_sends_supplement_reminder_for_stale_info_requested():
    # Arrange — info was requested from requester long ago
    past = timezone.now() - timedelta(days=7)
    req = DocumentRequestFactory(status=DocumentRequest.Status.INFO_REQUESTED)
    DocumentRequest.objects.filter(id=req.id).update(updated_at=past)

    # Act
    with patch("apps.documents.services._send_email") as mock_send:
        document_request_run_escalation(
            escalate_days=7,
            deposit_reminder_days=3,
            requester_reminder_days=5,
        )

    # Assert — reminder sent to requester
    assert mock_send.called
    sent_tos = [call.kwargs["to"] for call in mock_send.call_args_list]
    assert req.contact_email in sent_tos


@pytest.mark.django_db
def test_escalation_does_nothing_when_no_stale_requests():
    # Arrange — all requests are recent
    DocumentRequestFactory(status=DocumentRequest.Status.SUBMITTED)
    DocumentRequestFactory(status=DocumentRequest.Status.VALIDATED)

    # Act
    with patch("apps.documents.services._send_email") as mock_send:
        document_request_run_escalation(
            escalate_days=7,
            deposit_reminder_days=3,
            requester_reminder_days=5,
        )

    # Assert
    assert not mock_send.called

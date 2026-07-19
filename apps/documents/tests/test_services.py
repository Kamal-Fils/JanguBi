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
from apps.org.tests.factories import ParishFactory
from apps.users.enums import PastoralRole
from apps.users.tests.factories import (
    BaseUserFactory,
    ProfileFactory,
    StaffUserFactory,
)

from .factories import (
    DocumentRequestFactory,
    InvalidFileFactory,
    ValidFileFactory,
)


def _requester_with_parish():
    """Demandeur avec une paroisse principale (résolution target_parish OK)."""
    user = BaseUserFactory()
    ProfileFactory(user=user, primary_parish=ParishFactory())
    return user


def _priest_agent():
    """Agent signataire valide : prêtre (peut valider/déposer — Niv.2)."""
    return StaffUserFactory(pastoral_role=PastoralRole.PRETRE)


def _bishop_agent():
    """Agent épiscopal : évêque (peut signer les documents diocésains — Niv.3)."""
    return StaffUserFactory(pastoral_role=PastoralRole.EVEQUE)

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


def _data_with_parish(**extra):
    """Données de création valides : parish_id requis depuis B5c (FK obligatoire)."""
    return {**MINIMUM_DATA, "parish_id": ParishFactory().id, **extra}


# ---------------------------------------------------------------------------
# document_request_create
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_document_request_create_success():
    # Arrange
    requester = _requester_with_parish()
    data = _data_with_parish()

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


# --- « Autre » : le choix n'est valide qu'accompagné de sa précision libre ----


@pytest.mark.django_db
def test_create_other_document_type_requires_precision():
    # Arrange
    requester = _requester_with_parish()
    data = _data_with_parish(
        document_type=DocumentRequest.DocumentType.OTHER,
        document_type_free="   ",  # blancs seuls : ne renseigne rien
    )

    # Act & Assert
    with patch("apps.documents.services.transaction.on_commit"):
        with pytest.raises(ApplicationError, match="préciser le document"):
            document_request_create(requester=requester, data=data)


@pytest.mark.django_db
def test_create_other_document_type_with_precision_succeeds():
    # Arrange
    requester = _requester_with_parish()
    data = _data_with_parish(
        document_type=DocumentRequest.DocumentType.OTHER,
        document_type_free="Certificat de profession religieuse",
    )

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        result = document_request_create(requester=requester, data=data)

    # Assert
    assert result.document_type == DocumentRequest.DocumentType.OTHER
    assert result.document_type_free == "Certificat de profession religieuse"


@pytest.mark.django_db
def test_create_other_reason_requires_precision():
    # Arrange
    requester = _requester_with_parish()
    data = _data_with_parish(reason=DocumentRequest.RequestReason.OTHER, reason_free="")

    # Act & Assert
    with patch("apps.documents.services.transaction.on_commit"):
        with pytest.raises(ApplicationError, match="préciser le motif"):
            document_request_create(requester=requester, data=data)


@pytest.mark.django_db
def test_create_other_reason_with_precision_succeeds():
    # Arrange
    requester = _requester_with_parish()
    data = _data_with_parish(
        reason=DocumentRequest.RequestReason.OTHER,
        reason_free="Dossier de naturalisation",
    )

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        result = document_request_create(requester=requester, data=data)

    # Assert
    assert result.reason_free == "Dossier de naturalisation"


@pytest.mark.django_db
def test_precisions_are_dropped_when_choice_is_not_other():
    """Un texte résiduel d'un aller-retour du formulaire ne doit pas être stocké."""
    # Arrange — type/motif normaux, mais précisions présentes dans le payload
    requester = _requester_with_parish()
    data = _data_with_parish(
        document_type=DocumentRequest.DocumentType.BAPTISM,
        document_type_free="texte résiduel",
        reason=DocumentRequest.RequestReason.PERSONAL,
        reason_free="autre texte résiduel",
    )

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        result = document_request_create(requester=requester, data=data)

    # Assert
    assert result.document_type_free == ""
    assert result.reason_free == ""


# --- Cohérence pastorale type ↔ motif (apps.documents.constants) -------------


@pytest.mark.django_db
def test_create_rejects_godparent_reason_on_marriage_certificate():
    """Le cas signalé par le client : mariage religieux + parrain/marraine."""
    # Arrange
    requester = _requester_with_parish()
    data = _data_with_parish(
        document_type=DocumentRequest.DocumentType.RELIGIOUS_MARRIAGE,
        reason=DocumentRequest.RequestReason.GODPARENT,
        document_details={
            "spouse_full_name_groom": "Jean Diop",
            "spouse_full_name_bride": "Marie Faye",
        },
    )

    # Act & Assert
    with patch("apps.documents.services.transaction.on_commit"):
        with pytest.raises(ApplicationError, match="ne correspond pas au document"):
            document_request_create(requester=requester, data=data)


@pytest.mark.django_db
def test_create_rejects_marriage_reason_on_first_communion():
    # Arrange
    requester = _requester_with_parish()
    data = _data_with_parish(
        document_type=DocumentRequest.DocumentType.FIRST_COMMUNION,
        reason=DocumentRequest.RequestReason.RELIGIOUS_MARRIAGE,
    )

    # Act & Assert
    with patch("apps.documents.services.transaction.on_commit"):
        with pytest.raises(ApplicationError, match="ne correspond pas au document"):
            document_request_create(requester=requester, data=data)


@pytest.mark.django_db
def test_create_accepts_godparent_reason_on_baptism_certificate():
    # Arrange — le baptême est bien la pièce demandée pour un parrainage
    requester = _requester_with_parish()
    data = _data_with_parish(
        document_type=DocumentRequest.DocumentType.BAPTISM,
        reason=DocumentRequest.RequestReason.GODPARENT,
    )

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        result = document_request_create(requester=requester, data=data)

    # Assert
    assert result.reason == DocumentRequest.RequestReason.GODPARENT


@pytest.mark.django_db
def test_create_accepts_any_reason_on_other_document_type():
    # Arrange — catégorie ouverte : aucune restriction de motif
    requester = _requester_with_parish()
    data = _data_with_parish(
        document_type=DocumentRequest.DocumentType.OTHER,
        document_type_free="Attestation de profession de foi",
        reason=DocumentRequest.RequestReason.GODPARENT,
    )

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        result = document_request_create(requester=requester, data=data)

    # Assert
    assert result.reason == DocumentRequest.RequestReason.GODPARENT


# --- A5 — pas de repli silencieux sur la paroisse cible ---------------------


@pytest.mark.django_db
def test_invalid_parish_id_raises():
    # parish_id invalide → erreur explicite, jamais de repli silencieux sur la
    # paroisse principale.
    requester = _requester_with_parish()
    data = {**MINIMUM_DATA, "parish_id": 999999}

    with patch("apps.documents.services.transaction.on_commit"):
        with pytest.raises(ApplicationError, match="introuvable"):
            document_request_create(requester=requester, data=data)


@pytest.mark.django_db
def test_document_create_without_resolved_parish_raises():
    # B5c : pas de parish_id → rejet (jamais de demande orpheline target_parish=None).
    requester = BaseUserFactory()  # aucun profil → primary_parish None

    with patch("apps.documents.services.transaction.on_commit"):
        with pytest.raises(ApplicationError):
            document_request_create(requester=requester, data={**MINIMUM_DATA})


@pytest.mark.django_db
def test_document_request_create_logs_initial_status():
    # Arrange
    requester = _requester_with_parish()
    data = _data_with_parish()

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
    requester = _requester_with_parish()
    valid_file = ValidFileFactory(uploaded_by=requester)
    data = _data_with_parish(attachment_file_id=valid_file.id)

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        result = document_request_create(requester=requester, data=data)

    # Assert
    assert result.attachments.count() == 1
    assert result.attachments.first().file == valid_file


@pytest.mark.django_db
def test_document_request_create_raises_when_attachment_not_found():
    # Arrange
    requester = _requester_with_parish()
    data = _data_with_parish(attachment_file_id=uuid.uuid4())

    # Act & Assert
    with patch("apps.documents.services.transaction.on_commit"):
        with pytest.raises(ApplicationError, match="introuvable"):
            document_request_create(requester=requester, data=data)


@pytest.mark.django_db
def test_document_request_create_raises_when_attachment_not_finalized():
    # Arrange
    requester = _requester_with_parish()
    invalid_file = InvalidFileFactory(uploaded_by=requester)
    data = _data_with_parish(attachment_file_id=invalid_file.id)

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
    requester = _requester_with_parish()
    data = _data_with_parish(
        document_type=DocumentRequest.DocumentType.RELIGIOUS_MARRIAGE,
        document_details={
            "spouse_full_name_groom": "Jean Dupont",
            "spouse_full_name_bride": "Marie Ndiaye",
        },
    )

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
    # Arrange — la signature (Niv.2) exige un prêtre.
    agent = _priest_agent()
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.UNDER_VERIFICATION)

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        result = document_request_validate(request_obj=doc_request, agent=agent)

    # Assert
    assert result.status == DocumentRequest.Status.VALIDATED


@pytest.mark.django_db
def test_document_request_validate_creates_log():
    # Arrange
    agent = _priest_agent()
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
    agent = _priest_agent()
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.SUBMITTED)

    # Act & Assert
    with patch("apps.documents.services.transaction.on_commit"):
        with pytest.raises(ApplicationError, match="Transition invalide"):
            document_request_validate(request_obj=doc_request, agent=agent)


# --- Signature réservée au clergé (permissions-matrix.md §Documents) ---------


@pytest.mark.django_db
def test_document_request_validate_blocked_for_deacon():
    # Un diacre (church_admin + pastoral_role=diacre) ne peut PAS signer (Niv.2).
    agent = StaffUserFactory(role="church_admin", pastoral_role=PastoralRole.DIACRE)
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.UNDER_VERIFICATION)

    with patch("apps.documents.services.transaction.on_commit"):
        with pytest.raises(ApplicationError, match="réservé au clergé"):
            document_request_validate(request_obj=doc_request, agent=agent)
    doc_request.refresh_from_db()
    assert doc_request.status == DocumentRequest.Status.UNDER_VERIFICATION


@pytest.mark.django_db
def test_document_request_validate_blocked_for_lay_admin():
    # Un parish_admin laïc (aucun pastoral_role) ne peut PAS signer.
    agent = StaffUserFactory()  # parish_admin, pastoral_role=None
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.UNDER_VERIFICATION)

    with patch("apps.documents.services.transaction.on_commit"):
        with pytest.raises(ApplicationError, match="réservé au clergé"):
            document_request_validate(request_obj=doc_request, agent=agent)


@pytest.mark.django_db
def test_document_request_validate_blocked_for_super_admin_without_pastoral_role():
    # Le super-admin (pastoral_role=None) n'est pas un signataire pastoral.
    from apps.users.tests.factories import SuperAdminFactory

    agent = SuperAdminFactory()
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.UNDER_VERIFICATION)

    with patch("apps.documents.services.transaction.on_commit"):
        with pytest.raises(ApplicationError, match="réservé au clergé"):
            document_request_validate(request_obj=doc_request, agent=agent)


@pytest.mark.django_db
def test_document_request_validate_diocesan_type_requires_bishop():
    # Confirmation = document diocésain (Niv.3) : un prêtre ne suffit pas.
    priest = _priest_agent()
    doc_request = DocumentRequestFactory(
        status=DocumentRequest.Status.UNDER_VERIFICATION,
        document_type=DocumentRequest.DocumentType.CONFIRMATION,
    )

    with patch("apps.documents.services.transaction.on_commit"):
        with pytest.raises(ApplicationError, match="épiscopale"):
            document_request_validate(request_obj=doc_request, agent=priest)


@pytest.mark.django_db
def test_document_request_validate_diocesan_type_succeeds_for_bishop():
    # L'évêque peut signer un document diocésain (Niv.3).
    bishop = _bishop_agent()
    doc_request = DocumentRequestFactory(
        status=DocumentRequest.Status.UNDER_VERIFICATION,
        document_type=DocumentRequest.DocumentType.CONFIRMATION,
    )

    with patch("apps.documents.services.transaction.on_commit"):
        result = document_request_validate(request_obj=doc_request, agent=bishop)

    assert result.status == DocumentRequest.Status.VALIDATED


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
    # Arrange — le dépôt final (signature) exige un prêtre.
    agent = _priest_agent()
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
def test_document_request_deposit_document_blocked_for_lay_admin():
    # Un parish_admin laïc (aucun pastoral_role) ne peut PAS déposer le document final.
    agent = StaffUserFactory()  # parish_admin, pastoral_role=None
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.VALIDATED)
    valid_file = ValidFileFactory(uploaded_by=agent)

    with patch("apps.documents.services.transaction.on_commit"):
        with pytest.raises(ApplicationError, match="réservé au clergé"):
            document_request_deposit_document(
                request_obj=doc_request, agent=agent, file_id=valid_file.id
            )
    doc_request.refresh_from_db()
    assert doc_request.status == DocumentRequest.Status.VALIDATED


@pytest.mark.django_db
def test_document_request_deposit_document_raises_on_invalid_transition():
    # Arrange
    agent = _priest_agent()
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
    agent = _priest_agent()
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
    agent = _priest_agent()
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

# ---------------------------------------------------------------------------
# document_request_run_escalation — isolation transactionnelle
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_escalation_partial_failure_keeps_emails_of_previous_steps():
    """RÉGRESSION : une seule @transaction.atomic autour du run entier annulait
    les Email des étapes déjà exécutées dès qu'UNE étape échouait — le run
    n'envoyait alors aucune relance. Chaque demande a désormais sa transaction.
    """
    # Arrange — une demande stale par étape ; les deux premières doivent aboutir.
    agent = StaffUserFactory()
    submitted = DocumentRequestFactory(status=DocumentRequest.Status.SUBMITTED)
    verifying = DocumentRequestFactory(
        status=DocumentRequest.Status.UNDER_VERIFICATION, assigned_to=agent
    )
    validated = DocumentRequestFactory(status=DocumentRequest.Status.VALIDATED, assigned_to=agent)
    info_req = DocumentRequestFactory(status=DocumentRequest.Status.INFO_REQUESTED)

    past = timezone.now() - timedelta(days=30)
    DocumentRequest.objects.filter(
        id__in=[submitted.id, verifying.id, validated.id, info_req.id]
    ).update(updated_at=past)

    # L'étape « rappel dépôt » (3e boucle) explose.
    def _fail_on_deposit_reminder(*, to, subject, body_html):
        if "Rappel dépôt" in subject:
            raise RuntimeError("SMTP indisponible")

    # Act
    with patch("apps.documents.services._send_email", side_effect=_fail_on_deposit_reminder) as mock_send:
        document_request_run_escalation(
            escalate_days=7,
            deposit_reminder_days=3,
            requester_reminder_days=5,
        )

    # Assert — les étapes 1, 2 ET 4 ont bien été notifiées malgré l'échec de la 3e.
    subjects = [call.kwargs["subject"] for call in mock_send.call_args_list]
    assert any("est en attente" in s for s in subjects), "étape 1 (submitted) perdue"
    assert any("Vérification en attente" in s for s in subjects), "étape 2 perdue"
    assert any("Rappel complément" in s for s in subjects), "étape 4 non atteinte après l'échec"


@pytest.mark.django_db
def test_escalation_failure_on_one_request_does_not_stop_the_others():
    # Arrange — deux demandes stale au même statut ; la première échoue.
    past = timezone.now() - timedelta(days=30)
    first = DocumentRequestFactory(
        status=DocumentRequest.Status.INFO_REQUESTED, contact_email="boom@example.com"
    )
    second = DocumentRequestFactory(
        status=DocumentRequest.Status.INFO_REQUESTED, contact_email="ok@example.com"
    )
    DocumentRequest.objects.filter(id__in=[first.id, second.id]).update(updated_at=past)

    def _fail_for_first(*, to, subject, body_html):
        if to == "boom@example.com":
            raise RuntimeError("SMTP indisponible")

    # Act
    with patch("apps.documents.services._send_email", side_effect=_fail_for_first) as mock_send:
        document_request_run_escalation(
            escalate_days=7,
            deposit_reminder_days=3,
            requester_reminder_days=5,
        )

    # Assert — la seconde demande est bien relancée
    sent_tos = [call.kwargs["to"] for call in mock_send.call_args_list]
    assert "ok@example.com" in sent_tos


@pytest.mark.django_db
def test_escalation_persists_email_records_of_successful_steps():
    """L'Email des étapes réussies doit être COMMITÉ malgré l'échec d'une autre."""
    from apps.emails.models import Email

    # Arrange
    past = timezone.now() - timedelta(days=30)
    ok_req = DocumentRequestFactory(
        status=DocumentRequest.Status.INFO_REQUESTED, contact_email="persist@example.com"
    )
    ko_req = DocumentRequestFactory(status=DocumentRequest.Status.SUBMITTED)
    DocumentRequest.objects.filter(id__in=[ok_req.id, ko_req.id]).update(updated_at=past)

    # Act — l'étape « submitted » (1re) échoue APRÈS création de l'Email ;
    # l'étape « rappel complément » (4e) doit tout de même persister le sien.
    from apps.documents import services as documents_services

    real_send_email = documents_services._send_email

    def _send_then_maybe_fail(*, to, subject, body_html):
        real_send_email(to=to, subject=subject, body_html=body_html)
        if "est en attente" in subject:
            raise RuntimeError("Échec après création de l'Email")

    with (
        patch("apps.documents.services._send_email", side_effect=_send_then_maybe_fail),
        patch("apps.documents.services.transaction.on_commit"),
    ):
        document_request_run_escalation(
            escalate_days=7,
            deposit_reminder_days=3,
            requester_reminder_days=5,
        )

    # Assert — l'Email de l'étape réussie survit ; celui de l'étape échouée a été annulé.
    assert Email.objects.filter(to="persist@example.com").exists()
    assert not Email.objects.filter(to=ko_req.contact_email).exists()

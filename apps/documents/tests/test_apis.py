"""
Tests des API documents — HackSoft Styleguide.
Pattern AAA (Arrange / Act / Assert) sur chaque test.
Chaque endpoint est couvert : succès, 401 non authentifié, 400 payload invalide,
403 interdit (mauvais rôle / mauvais propriétaire).
"""

import uuid
from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.documents.models import DocumentRequest, DocumentRequestStatusLog
from apps.users.tests.factories import BaseUserFactory, StaffUserFactory

from .factories import DocumentRequestFactory, InternalNoteFactory, ValidFileFactory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fidele_client():
    client = APIClient()
    user = BaseUserFactory()
    client.force_authenticate(user=user)
    client._user = user
    return client


@pytest.fixture
def admin_client():
    client = APIClient()
    user = StaffUserFactory()
    client.force_authenticate(user=user)
    client._user = user
    return client


@pytest.fixture
def anon_client():
    return APIClient()


VALID_CREATE_PAYLOAD = {
    "document_type": "baptism",
    "reason": "personal",
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
# DocumentRequestListCreateApi — GET (list)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_document_request_list_returns_200_for_fidele(fidele_client):
    # Arrange
    DocumentRequestFactory(requester=fidele_client._user)
    url = reverse("api:documents:document-request-list-create")

    # Act
    response = fidele_client.get(url)

    # Assert
    assert response.status_code == 200
    assert response.data["count"] == 1


@pytest.mark.django_db
def test_document_request_list_returns_401_for_anonymous(anon_client):
    # Arrange
    url = reverse("api:documents:document-request-list-create")

    # Act
    response = anon_client.get(url)

    # Assert
    assert response.status_code == 401


@pytest.mark.django_db
def test_document_request_list_fidele_sees_only_own_requests(fidele_client):
    # Arrange
    other = BaseUserFactory()
    DocumentRequestFactory(requester=fidele_client._user)
    DocumentRequestFactory(requester=other)
    url = reverse("api:documents:document-request-list-create")

    # Act
    response = fidele_client.get(url)

    # Assert
    assert response.status_code == 200
    assert response.data["count"] == 1


# ---------------------------------------------------------------------------
# DocumentRequestListCreateApi — POST (create)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_document_request_create_returns_201(fidele_client):
    # Arrange
    url = reverse("api:documents:document-request-list-create")

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        response = fidele_client.post(url, VALID_CREATE_PAYLOAD, format="json")

    # Assert
    assert response.status_code == 201
    assert response.data["status"] == DocumentRequest.Status.SUBMITTED
    assert response.data["document_type"] == "baptism"
    assert "reference" in response.data


@pytest.mark.django_db
def test_document_request_create_returns_401_for_anonymous(anon_client):
    # Arrange
    url = reverse("api:documents:document-request-list-create")

    # Act
    response = anon_client.post(url, VALID_CREATE_PAYLOAD, format="json")

    # Assert
    assert response.status_code == 401


@pytest.mark.django_db
def test_document_request_create_returns_400_when_consent_not_given(fidele_client):
    # Arrange
    url = reverse("api:documents:document-request-list-create")
    payload = {**VALID_CREATE_PAYLOAD, "consent_given": False}

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        response = fidele_client.post(url, payload, format="json")

    # Assert
    assert response.status_code == 400
    assert "consent_given" in response.data["detail"]


@pytest.mark.django_db
def test_document_request_create_returns_400_on_empty_payload(fidele_client):
    # Arrange
    url = reverse("api:documents:document-request-list-create")

    # Act
    response = fidele_client.post(url, {}, format="json")

    # Assert
    assert response.status_code == 400


@pytest.mark.django_db
def test_document_request_create_returns_400_when_religious_marriage_missing_details(fidele_client):
    # Arrange
    url = reverse("api:documents:document-request-list-create")
    payload = {
        **VALID_CREATE_PAYLOAD,
        "document_type": "religious_marriage",
        "document_details": {},
    }

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        response = fidele_client.post(url, payload, format="json")

    # Assert
    assert response.status_code == 400
    assert "detail" in response.data


# ---------------------------------------------------------------------------
# DocumentRequestDetailApi — GET
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_document_request_detail_returns_200_for_owner(fidele_client):
    # Arrange
    doc_request = DocumentRequestFactory(requester=fidele_client._user)
    url = reverse("api:documents:document-request-detail", kwargs={"request_id": doc_request.id})

    # Act
    response = fidele_client.get(url)

    # Assert
    assert response.status_code == 200
    assert str(response.data["id"]) == str(doc_request.id)


@pytest.mark.django_db
def test_document_request_detail_returns_200_for_admin(admin_client):
    # Arrange
    fidele = BaseUserFactory()
    doc_request = DocumentRequestFactory(requester=fidele)
    url = reverse("api:documents:document-request-detail", kwargs={"request_id": doc_request.id})

    # Act
    response = admin_client.get(url)

    # Assert
    assert response.status_code == 200
    assert str(response.data["id"]) == str(doc_request.id)


@pytest.mark.django_db
def test_document_request_detail_returns_401_for_anonymous(anon_client):
    # Arrange
    doc_request = DocumentRequestFactory()
    url = reverse("api:documents:document-request-detail", kwargs={"request_id": doc_request.id})

    # Act
    response = anon_client.get(url)

    # Assert
    assert response.status_code == 401


@pytest.mark.django_db
def test_document_request_detail_returns_400_when_fidele_accesses_other_request(fidele_client):
    # Arrange — selector raises ApplicationError for non-owner non-admin → _error → 400
    other_owner = BaseUserFactory()
    doc_request = DocumentRequestFactory(requester=other_owner)
    url = reverse("api:documents:document-request-detail", kwargs={"request_id": doc_request.id})

    # Act
    response = fidele_client.get(url)

    # Assert
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# DocumentRequestSupplementApi — POST
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_document_request_supplement_returns_200(fidele_client):
    # Arrange
    doc_request = DocumentRequestFactory(
        requester=fidele_client._user,
        status=DocumentRequest.Status.INFO_REQUESTED,
    )
    url = reverse(
        "api:documents:document-request-supplement", kwargs={"request_id": doc_request.id}
    )

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        response = fidele_client.post(
            url, {"additional_info": "Voici les informations."}, format="json"
        )

    # Assert
    assert response.status_code == 200
    assert response.data["status"] == DocumentRequest.Status.UNDER_VERIFICATION


@pytest.mark.django_db
def test_document_request_supplement_returns_401_for_anonymous(anon_client):
    # Arrange
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.INFO_REQUESTED)
    url = reverse(
        "api:documents:document-request-supplement", kwargs={"request_id": doc_request.id}
    )

    # Act
    response = anon_client.post(url, {"additional_info": "info"}, format="json")

    # Assert
    assert response.status_code == 401


@pytest.mark.django_db
def test_document_request_supplement_returns_403_for_non_owner(fidele_client):
    # Arrange
    other_owner = BaseUserFactory()
    doc_request = DocumentRequestFactory(
        requester=other_owner, status=DocumentRequest.Status.INFO_REQUESTED
    )
    url = reverse(
        "api:documents:document-request-supplement", kwargs={"request_id": doc_request.id}
    )

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        response = fidele_client.post(url, {"additional_info": "info"}, format="json")

    # Assert
    assert response.status_code == 403


@pytest.mark.django_db
def test_document_request_supplement_returns_400_when_status_not_info_requested(fidele_client):
    # Arrange
    doc_request = DocumentRequestFactory(
        requester=fidele_client._user,
        status=DocumentRequest.Status.SUBMITTED,
    )
    url = reverse(
        "api:documents:document-request-supplement", kwargs={"request_id": doc_request.id}
    )

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        response = fidele_client.post(url, {"additional_info": "info"}, format="json")

    # Assert
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# AdminDocumentRequestListApi — GET
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_document_request_list_returns_200_for_admin(admin_client):
    # Arrange
    DocumentRequestFactory()
    DocumentRequestFactory()
    url = reverse("api:documents:admin-document-request-list")

    # Act
    response = admin_client.get(url)

    # Assert
    assert response.status_code == 200
    assert response.data["count"] == 2


@pytest.mark.django_db
def test_admin_document_request_list_returns_401_for_anonymous(anon_client):
    # Arrange
    url = reverse("api:documents:admin-document-request-list")

    # Act
    response = anon_client.get(url)

    # Assert
    assert response.status_code == 401


@pytest.mark.django_db
def test_admin_document_request_list_returns_403_for_fidele(fidele_client):
    # Arrange
    url = reverse("api:documents:admin-document-request-list")

    # Act
    response = fidele_client.get(url)

    # Assert
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# AdminDocumentRequestDetailApi — GET
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_document_request_detail_returns_200_for_admin(admin_client):
    # Arrange
    doc_request = DocumentRequestFactory()
    url = reverse(
        "api:documents:admin-document-request-detail", kwargs={"request_id": doc_request.id}
    )

    # Act
    response = admin_client.get(url)

    # Assert
    assert response.status_code == 200
    assert str(response.data["id"]) == str(doc_request.id)


@pytest.mark.django_db
def test_admin_document_request_detail_returns_401_for_anonymous(anon_client):
    # Arrange
    doc_request = DocumentRequestFactory()
    url = reverse(
        "api:documents:admin-document-request-detail", kwargs={"request_id": doc_request.id}
    )

    # Act
    response = anon_client.get(url)

    # Assert
    assert response.status_code == 401


@pytest.mark.django_db
def test_admin_document_request_detail_returns_403_for_fidele(fidele_client):
    # Arrange
    doc_request = DocumentRequestFactory()
    url = reverse(
        "api:documents:admin-document-request-detail", kwargs={"request_id": doc_request.id}
    )

    # Act
    response = fidele_client.get(url)

    # Assert
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# AdminStartVerificationApi — POST
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_start_verification_returns_200(admin_client):
    # Arrange
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.SUBMITTED)
    url = reverse(
        "api:documents:admin-document-start-verification", kwargs={"request_id": doc_request.id}
    )

    # Act
    response = admin_client.post(url)

    # Assert
    assert response.status_code == 200
    assert response.data["status"] == DocumentRequest.Status.UNDER_VERIFICATION


@pytest.mark.django_db
def test_admin_start_verification_returns_401_for_anonymous(anon_client):
    # Arrange
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.SUBMITTED)
    url = reverse(
        "api:documents:admin-document-start-verification", kwargs={"request_id": doc_request.id}
    )

    # Act
    response = anon_client.post(url)

    # Assert
    assert response.status_code == 401


@pytest.mark.django_db
def test_admin_start_verification_returns_403_for_fidele(fidele_client):
    # Arrange
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.SUBMITTED)
    url = reverse(
        "api:documents:admin-document-start-verification", kwargs={"request_id": doc_request.id}
    )

    # Act
    response = fidele_client.post(url)

    # Assert
    assert response.status_code == 403


@pytest.mark.django_db
def test_admin_start_verification_returns_400_on_invalid_transition(admin_client):
    # Arrange
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.VALIDATED)
    url = reverse(
        "api:documents:admin-document-start-verification", kwargs={"request_id": doc_request.id}
    )

    # Act
    response = admin_client.post(url)

    # Assert
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# AdminRequestInfoApi — POST
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_request_info_returns_200(admin_client):
    # Arrange
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.UNDER_VERIFICATION)
    url = reverse(
        "api:documents:admin-document-request-info", kwargs={"request_id": doc_request.id}
    )

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        response = admin_client.post(
            url, {"comment": "Merci de fournir votre acte de naissance."}, format="json"
        )

    # Assert
    assert response.status_code == 200
    assert response.data["status"] == DocumentRequest.Status.INFO_REQUESTED


@pytest.mark.django_db
def test_admin_request_info_returns_401_for_anonymous(anon_client):
    # Arrange
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.UNDER_VERIFICATION)
    url = reverse(
        "api:documents:admin-document-request-info", kwargs={"request_id": doc_request.id}
    )

    # Act
    response = anon_client.post(url, {"comment": "commentaire"}, format="json")

    # Assert
    assert response.status_code == 401


@pytest.mark.django_db
def test_admin_request_info_returns_403_for_fidele(fidele_client):
    # Arrange
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.UNDER_VERIFICATION)
    url = reverse(
        "api:documents:admin-document-request-info", kwargs={"request_id": doc_request.id}
    )

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        response = fidele_client.post(url, {"comment": "commentaire"}, format="json")

    # Assert
    assert response.status_code == 403


@pytest.mark.django_db
def test_admin_request_info_returns_400_on_invalid_transition(admin_client):
    # Arrange
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.SUBMITTED)
    url = reverse(
        "api:documents:admin-document-request-info", kwargs={"request_id": doc_request.id}
    )

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        response = admin_client.post(url, {"comment": "commentaire"}, format="json")

    # Assert
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# AdminValidateApi — POST
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_validate_returns_200(admin_client):
    # Arrange
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.UNDER_VERIFICATION)
    url = reverse(
        "api:documents:admin-document-validate", kwargs={"request_id": doc_request.id}
    )

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        response = admin_client.post(url)

    # Assert
    assert response.status_code == 200
    assert response.data["status"] == DocumentRequest.Status.VALIDATED


@pytest.mark.django_db
def test_admin_validate_returns_401_for_anonymous(anon_client):
    # Arrange
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.UNDER_VERIFICATION)
    url = reverse(
        "api:documents:admin-document-validate", kwargs={"request_id": doc_request.id}
    )

    # Act
    response = anon_client.post(url)

    # Assert
    assert response.status_code == 401


@pytest.mark.django_db
def test_admin_validate_returns_403_for_fidele(fidele_client):
    # Arrange
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.UNDER_VERIFICATION)
    url = reverse(
        "api:documents:admin-document-validate", kwargs={"request_id": doc_request.id}
    )

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        response = fidele_client.post(url)

    # Assert
    assert response.status_code == 403


@pytest.mark.django_db
def test_admin_validate_returns_400_on_invalid_transition(admin_client):
    # Arrange
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.SUBMITTED)
    url = reverse(
        "api:documents:admin-document-validate", kwargs={"request_id": doc_request.id}
    )

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        response = admin_client.post(url)

    # Assert
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# AdminRejectApi — POST
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_reject_returns_200(admin_client):
    # Arrange
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.UNDER_VERIFICATION)
    url = reverse("api:documents:admin-document-reject", kwargs={"request_id": doc_request.id})

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        response = admin_client.post(
            url, {"reason": "Document introuvable dans les archives."}, format="json"
        )

    # Assert
    assert response.status_code == 200
    assert response.data["status"] == DocumentRequest.Status.REJECTED


@pytest.mark.django_db
def test_admin_reject_returns_401_for_anonymous(anon_client):
    # Arrange
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.UNDER_VERIFICATION)
    url = reverse("api:documents:admin-document-reject", kwargs={"request_id": doc_request.id})

    # Act
    response = anon_client.post(url, {"reason": "motif"}, format="json")

    # Assert
    assert response.status_code == 401


@pytest.mark.django_db
def test_admin_reject_returns_403_for_fidele(fidele_client):
    # Arrange
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.UNDER_VERIFICATION)
    url = reverse("api:documents:admin-document-reject", kwargs={"request_id": doc_request.id})

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        response = fidele_client.post(url, {"reason": "motif"}, format="json")

    # Assert
    assert response.status_code == 403


@pytest.mark.django_db
def test_admin_reject_returns_400_when_reason_missing(admin_client):
    # Arrange
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.UNDER_VERIFICATION)
    url = reverse("api:documents:admin-document-reject", kwargs={"request_id": doc_request.id})

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        response = admin_client.post(url, {}, format="json")

    # Assert
    assert response.status_code == 400


@pytest.mark.django_db
def test_admin_reject_returns_400_on_invalid_transition(admin_client):
    # Arrange
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.SUBMITTED)
    url = reverse("api:documents:admin-document-reject", kwargs={"request_id": doc_request.id})

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        response = admin_client.post(url, {"reason": "motif valide"}, format="json")

    # Assert
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# AdminDepositApi — POST
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_deposit_returns_200(admin_client):
    # Arrange
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.VALIDATED)
    valid_file = ValidFileFactory(uploaded_by=admin_client._user)
    url = reverse("api:documents:admin-document-deposit", kwargs={"request_id": doc_request.id})

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        response = admin_client.post(
            url,
            {"file_id": str(valid_file.id), "label": "Certificat de baptême"},
            format="json",
        )

    # Assert
    assert response.status_code == 200
    assert response.data["status"] == DocumentRequest.Status.DOCUMENT_DEPOSITED


@pytest.mark.django_db
def test_admin_deposit_returns_401_for_anonymous(anon_client):
    # Arrange
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.VALIDATED)
    url = reverse("api:documents:admin-document-deposit", kwargs={"request_id": doc_request.id})

    # Act
    response = anon_client.post(url, {"file_id": str(uuid.uuid4())}, format="json")

    # Assert
    assert response.status_code == 401


@pytest.mark.django_db
def test_admin_deposit_returns_403_for_fidele(fidele_client):
    # Arrange
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.VALIDATED)
    url = reverse("api:documents:admin-document-deposit", kwargs={"request_id": doc_request.id})

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        response = fidele_client.post(url, {"file_id": str(uuid.uuid4())}, format="json")

    # Assert
    assert response.status_code == 403


@pytest.mark.django_db
def test_admin_deposit_returns_400_on_missing_file_id(admin_client):
    # Arrange
    doc_request = DocumentRequestFactory(status=DocumentRequest.Status.VALIDATED)
    url = reverse("api:documents:admin-document-deposit", kwargs={"request_id": doc_request.id})

    # Act
    with patch("apps.documents.services.transaction.on_commit"):
        response = admin_client.post(url, {}, format="json")

    # Assert
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# AdminNotesApi — GET / POST
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_notes_get_returns_200(admin_client):
    # Arrange
    doc_request = DocumentRequestFactory()
    InternalNoteFactory(request=doc_request, author=admin_client._user)
    url = reverse("api:documents:admin-document-notes", kwargs={"request_id": doc_request.id})

    # Act
    response = admin_client.get(url)

    # Assert
    assert response.status_code == 200
    assert len(response.data) == 1


@pytest.mark.django_db
def test_admin_notes_post_returns_201(admin_client):
    # Arrange
    doc_request = DocumentRequestFactory()
    url = reverse("api:documents:admin-document-notes", kwargs={"request_id": doc_request.id})

    # Act
    response = admin_client.post(url, {"content": "Vérification en cours."}, format="json")

    # Assert
    assert response.status_code == 201
    assert response.data["content"] == "Vérification en cours."


@pytest.mark.django_db
def test_admin_notes_post_returns_401_for_anonymous(anon_client):
    # Arrange
    doc_request = DocumentRequestFactory()
    url = reverse("api:documents:admin-document-notes", kwargs={"request_id": doc_request.id})

    # Act
    response = anon_client.post(url, {"content": "note"}, format="json")

    # Assert
    assert response.status_code == 401


@pytest.mark.django_db
def test_admin_notes_post_returns_403_for_fidele(fidele_client):
    # Arrange
    doc_request = DocumentRequestFactory()
    url = reverse("api:documents:admin-document-notes", kwargs={"request_id": doc_request.id})

    # Act
    response = fidele_client.post(url, {"content": "note"}, format="json")

    # Assert
    assert response.status_code == 403


@pytest.mark.django_db
def test_admin_notes_post_returns_400_on_missing_content(admin_client):
    # Arrange
    doc_request = DocumentRequestFactory()
    url = reverse("api:documents:admin-document-notes", kwargs={"request_id": doc_request.id})

    # Act
    response = admin_client.post(url, {}, format="json")

    # Assert
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# AdminLogsApi — GET
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_logs_get_returns_200(admin_client):
    # Arrange
    doc_request = DocumentRequestFactory()
    DocumentRequestStatusLog.objects.create(
        request=doc_request,
        from_status="",
        to_status=DocumentRequest.Status.SUBMITTED,
        changed_by=admin_client._user,
    )
    url = reverse("api:documents:admin-document-logs", kwargs={"request_id": doc_request.id})

    # Act
    response = admin_client.get(url)

    # Assert
    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["to_status"] == DocumentRequest.Status.SUBMITTED


@pytest.mark.django_db
def test_admin_logs_get_returns_401_for_anonymous(anon_client):
    # Arrange
    doc_request = DocumentRequestFactory()
    url = reverse("api:documents:admin-document-logs", kwargs={"request_id": doc_request.id})

    # Act
    response = anon_client.get(url)

    # Assert
    assert response.status_code == 401


@pytest.mark.django_db
def test_admin_logs_get_returns_403_for_fidele(fidele_client):
    # Arrange
    doc_request = DocumentRequestFactory()
    url = reverse("api:documents:admin-document-logs", kwargs={"request_id": doc_request.id})

    # Act
    response = fidele_client.get(url)

    # Assert
    assert response.status_code == 403

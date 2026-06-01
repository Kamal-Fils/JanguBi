"""
Tests des selectors documents — HackSoft Styleguide.
Pattern AAA (Arrange / Act / Assert) sur chaque test.
"""

import uuid

import pytest

from apps.core.exceptions import ApplicationError
from apps.documents.models import DocumentRequest, DocumentRequestStatusLog
from apps.documents.selectors import (
    document_request_attachment_list,
    document_request_get,
    document_request_internal_note_list,
    document_request_list,
    document_request_status_log_list,
)
from apps.org.tests.factories import ParishFactory
from apps.users.enums import RoleScope, UserRole
from apps.users.models import RoleAssignment
from apps.users.tests.factories import AdminUserFactory, BaseUserFactory, StaffUserFactory

from .factories import (
    DocumentRequestAttachmentFactory,
    DocumentRequestFactory,
    InternalNoteFactory,
)


# ---------------------------------------------------------------------------
# document_request_list
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_document_request_list_returns_all_for_admin():
    # Arrange
    admin = AdminUserFactory()
    user1 = BaseUserFactory()
    user2 = BaseUserFactory()
    DocumentRequestFactory(requester=user1)
    DocumentRequestFactory(requester=user2)

    # Act
    result = document_request_list(user=admin)

    # Assert
    assert result.count() == 2


@pytest.mark.django_db
def test_document_request_list_returns_only_own_for_fidele():
    # Arrange
    fidele = BaseUserFactory()
    other = BaseUserFactory()
    DocumentRequestFactory(requester=fidele)
    DocumentRequestFactory(requester=other)

    # Act
    result = document_request_list(user=fidele)

    # Assert
    assert result.count() == 1
    assert result.first().requester == fidele


@pytest.mark.django_db
def test_document_request_list_filter_by_status():
    # Arrange
    admin = AdminUserFactory()
    DocumentRequestFactory(status=DocumentRequest.Status.SUBMITTED)
    DocumentRequestFactory(status=DocumentRequest.Status.VALIDATED)

    # Act
    result = document_request_list(
        user=admin, filters={"status": DocumentRequest.Status.SUBMITTED}
    )

    # Assert
    assert result.count() == 1
    assert result.first().status == DocumentRequest.Status.SUBMITTED


@pytest.mark.django_db
def test_document_request_list_filter_by_document_type():
    # Arrange
    admin = AdminUserFactory()
    DocumentRequestFactory(document_type=DocumentRequest.DocumentType.BAPTISM)
    DocumentRequestFactory(document_type=DocumentRequest.DocumentType.CONFIRMATION)

    # Act
    result = document_request_list(
        user=admin, filters={"document_type": DocumentRequest.DocumentType.BAPTISM}
    )

    # Assert
    assert result.count() == 1
    assert result.first().document_type == DocumentRequest.DocumentType.BAPTISM


@pytest.mark.django_db
def test_document_request_list_filter_by_parish_name_icontains():
    # Arrange
    admin = AdminUserFactory()
    DocumentRequestFactory(parish_name="Saint-Pierre")
    DocumentRequestFactory(parish_name="Notre-Dame")

    # Act
    result = document_request_list(user=admin, filters={"parish_name": "Saint"})

    # Assert
    assert result.count() == 1
    assert "Saint" in result.first().parish_name


@pytest.mark.django_db
def test_document_request_list_filter_by_search_last_name():
    # Arrange
    admin = AdminUserFactory()
    DocumentRequestFactory(requester_last_name="Diallo")
    DocumentRequestFactory(requester_last_name="Ndiaye")

    # Act
    result = document_request_list(user=admin, filters={"search": "Dial"})

    # Assert
    assert result.count() == 1
    assert result.first().requester_last_name == "Diallo"


@pytest.mark.django_db
def test_document_request_list_filter_by_assigned_to_id():
    # Arrange
    admin = AdminUserFactory()
    agent = StaffUserFactory()
    DocumentRequestFactory(assigned_to=agent)
    DocumentRequestFactory(assigned_to=None)

    # Act
    result = document_request_list(user=admin, filters={"assigned_to_id": str(agent.id)})

    # Assert
    assert result.count() == 1
    assert result.first().assigned_to == agent


@pytest.mark.django_db
def test_document_request_list_returns_empty_when_fidele_has_no_requests():
    # Arrange
    fidele = BaseUserFactory()

    # Act
    result = document_request_list(user=fidele)

    # Assert
    assert result.count() == 0


@pytest.mark.django_db
def test_document_request_list_ordered_by_created_at_desc():
    # Arrange
    admin = AdminUserFactory()
    first = DocumentRequestFactory()
    second = DocumentRequestFactory()

    # Act
    result = document_request_list(user=admin)

    # Assert — most recent first
    ids = list(result.values_list("id", flat=True))
    assert ids[0] == second.id
    assert ids[1] == first.id


@pytest.mark.django_db
def test_document_request_list_no_filters_returns_all_for_admin():
    # Arrange
    admin = AdminUserFactory()
    DocumentRequestFactory()
    DocumentRequestFactory()
    DocumentRequestFactory()

    # Act
    result = document_request_list(user=admin, filters=None)

    # Assert
    assert result.count() == 3


@pytest.mark.django_db
def test_document_request_list_empty_for_admin_without_role_assignment():
    # FAIL-CLOSED (Lot 1 / Phase 5) : un admin (role=parish_admin) SANS
    # RoleAssignment ne voit RIEN — avant : repli legacy fail-open → voyait tout.
    admin = StaffUserFactory()  # role=parish_admin, aucune RoleAssignment
    DocumentRequestFactory()
    DocumentRequestFactory()

    result = document_request_list(user=admin)

    assert result.count() == 0


@pytest.mark.django_db
def test_document_request_list_scoped_to_cure_parish():
    # Curé (RoleAssignment parish_admin/P) ne voit que les demandes de SA paroisse.
    parish = ParishFactory()
    other_parish = ParishFactory()
    cure = BaseUserFactory(role=UserRole.FIDELE)
    RoleAssignment.objects.create(
        user=cure,
        role=UserRole.PARISH_ADMIN,
        scope=RoleScope.PARISH,
        parish=parish,
        is_active=True,
    )
    mine = DocumentRequestFactory(target_parish=parish)
    DocumentRequestFactory(target_parish=other_parish)

    result = document_request_list(user=cure)

    assert result.count() == 1
    assert result.first().id == mine.id


# ---------------------------------------------------------------------------
# document_request_get
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_document_request_get_success_for_owner():
    # Arrange
    fidele = BaseUserFactory()
    doc_request = DocumentRequestFactory(requester=fidele)

    # Act
    result = document_request_get(request_id=doc_request.id, user=fidele)

    # Assert
    assert result.id == doc_request.id
    assert result.requester == fidele


@pytest.mark.django_db
def test_document_request_get_success_for_admin():
    # Arrange
    admin = AdminUserFactory()
    fidele = BaseUserFactory()
    doc_request = DocumentRequestFactory(requester=fidele)

    # Act
    result = document_request_get(request_id=doc_request.id, user=admin)

    # Assert
    assert result.id == doc_request.id


@pytest.mark.django_db
def test_document_request_get_raises_when_not_found():
    # Arrange
    fidele = BaseUserFactory()
    nonexistent_id = uuid.uuid4()

    # Act & Assert
    with pytest.raises(ApplicationError, match="introuvable"):
        document_request_get(request_id=nonexistent_id, user=fidele)


@pytest.mark.django_db
def test_document_request_get_raises_when_fidele_accesses_other_users_request():
    # Arrange
    owner = BaseUserFactory()
    other_fidele = BaseUserFactory()
    doc_request = DocumentRequestFactory(requester=owner)

    # Act & Assert — selector filters by requester for non-admins,
    # so the get() raises DoesNotExist → wrapped as ApplicationError
    with pytest.raises(ApplicationError, match="introuvable"):
        document_request_get(request_id=doc_request.id, user=other_fidele)


# ---------------------------------------------------------------------------
# document_request_status_log_list
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_document_request_status_log_list_returns_logs_ordered_by_created_at():
    # Arrange
    doc_request = DocumentRequestFactory()
    log1 = DocumentRequestStatusLog.objects.create(
        request=doc_request,
        from_status="",
        to_status=DocumentRequest.Status.SUBMITTED,
        changed_by=doc_request.requester,
    )
    log2 = DocumentRequestStatusLog.objects.create(
        request=doc_request,
        from_status=DocumentRequest.Status.SUBMITTED,
        to_status=DocumentRequest.Status.UNDER_VERIFICATION,
        changed_by=doc_request.requester,
    )

    # Act
    result = document_request_status_log_list(request_obj=doc_request)

    # Assert
    ids = list(result.values_list("id", flat=True))
    assert ids[0] == log1.id
    assert ids[1] == log2.id


@pytest.mark.django_db
def test_document_request_status_log_list_scoped_to_request():
    # Arrange
    request_a = DocumentRequestFactory()
    request_b = DocumentRequestFactory()
    DocumentRequestStatusLog.objects.create(
        request=request_a,
        from_status="",
        to_status=DocumentRequest.Status.SUBMITTED,
    )
    DocumentRequestStatusLog.objects.create(
        request=request_b,
        from_status="",
        to_status=DocumentRequest.Status.SUBMITTED,
    )

    # Act
    result = document_request_status_log_list(request_obj=request_a)

    # Assert
    assert result.count() == 1
    assert result.first().request == request_a


@pytest.mark.django_db
def test_document_request_status_log_list_returns_empty_when_no_logs():
    # Arrange
    doc_request = DocumentRequestFactory()

    # Act
    result = document_request_status_log_list(request_obj=doc_request)

    # Assert
    assert result.count() == 0


# ---------------------------------------------------------------------------
# document_request_internal_note_list
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_document_request_internal_note_list_returns_notes():
    # Arrange
    doc_request = DocumentRequestFactory()
    note = InternalNoteFactory(request=doc_request)

    # Act
    result = document_request_internal_note_list(request_obj=doc_request)

    # Assert
    assert result.count() == 1
    assert result.first().id == note.id


@pytest.mark.django_db
def test_document_request_internal_note_list_scoped_to_request():
    # Arrange
    request_a = DocumentRequestFactory()
    request_b = DocumentRequestFactory()
    InternalNoteFactory(request=request_a)
    InternalNoteFactory(request=request_b)

    # Act
    result = document_request_internal_note_list(request_obj=request_a)

    # Assert
    assert result.count() == 1
    assert result.first().request == request_a


@pytest.mark.django_db
def test_document_request_internal_note_list_returns_empty_when_none():
    # Arrange
    doc_request = DocumentRequestFactory()

    # Act
    result = document_request_internal_note_list(request_obj=doc_request)

    # Assert
    assert result.count() == 0


# ---------------------------------------------------------------------------
# document_request_attachment_list
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_document_request_attachment_list_returns_attachments():
    # Arrange
    doc_request = DocumentRequestFactory()
    attachment = DocumentRequestAttachmentFactory(request=doc_request)

    # Act
    result = document_request_attachment_list(request_obj=doc_request)

    # Assert
    assert result.count() == 1
    assert result.first().id == attachment.id


@pytest.mark.django_db
def test_document_request_attachment_list_scoped_to_request():
    # Arrange
    request_a = DocumentRequestFactory()
    request_b = DocumentRequestFactory()
    DocumentRequestAttachmentFactory(request=request_a)
    DocumentRequestAttachmentFactory(request=request_b)

    # Act
    result = document_request_attachment_list(request_obj=request_a)

    # Assert
    assert result.count() == 1
    assert result.first().request == request_a


@pytest.mark.django_db
def test_document_request_attachment_list_returns_empty_when_none():
    # Arrange
    doc_request = DocumentRequestFactory()

    # Act
    result = document_request_attachment_list(request_obj=doc_request)

    # Assert
    assert result.count() == 0

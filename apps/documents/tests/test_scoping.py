import pytest

from apps.documents.selectors import document_request_agent_recipients, document_request_list
from apps.org.tests.factories import ParishFactory
from apps.users.enums import RoleScope, UserRole
from apps.users.services_roles import role_assignment_create
from apps.users.tests.factories import BaseUserFactory

from .factories import DocumentRequestFactory


@pytest.mark.django_db
def test_cure_sees_only_own_parish_documents():
    # Arrange — deux paroisses, une demande chacune
    parish_a = ParishFactory()
    parish_b = ParishFactory()
    doc_a = DocumentRequestFactory(requester=BaseUserFactory(), target_parish=parish_a)
    DocumentRequestFactory(requester=BaseUserFactory(), target_parish=parish_b)

    cure_a = BaseUserFactory(role=UserRole.PARISH_ADMIN)
    role_assignment_create(
        user=cure_a, role=UserRole.PARISH_ADMIN, scope=RoleScope.PARISH,
        parish=parish_a, is_principal=True,
    )

    # Act
    result = list(document_request_list(user=cure_a))

    # Assert — le curé de A ne voit pas les demandes de B
    assert result == [doc_a]


@pytest.mark.django_db
def test_recipients_route_to_parish_clergy():
    # Arrange
    parish = ParishFactory()
    cure = BaseUserFactory(role=UserRole.PARISH_ADMIN)
    role_assignment_create(
        user=cure, role=UserRole.PARISH_ADMIN, scope=RoleScope.PARISH,
        parish=parish, is_principal=True,
    )
    doc = DocumentRequestFactory(requester=BaseUserFactory(), target_parish=parish)

    # Act
    recipients = document_request_agent_recipients(request_obj=doc)

    # Assert — la demande est routée au curé de la paroisse, pas à tous les admins
    assert cure in recipients

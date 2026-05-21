"""
Factories factory_boy pour les tests documents.
Réutilise BaseUserFactory depuis apps/users/tests/factories.py.
"""

import datetime

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.documents.models import DocumentRequest, DocumentRequestAttachment, InternalNote
from apps.files.models import File
from apps.users.tests.factories import BaseUserFactory, StaffUserFactory


class DocumentRequestFactory(DjangoModelFactory):
    """Crée une demande de document soumise par un fidèle par défaut."""

    class Meta:
        model = DocumentRequest

    requester = factory.SubFactory(BaseUserFactory)
    reference = factory.Sequence(lambda n: f"DOC-20260427-{n:06d}")
    document_type = DocumentRequest.DocumentType.BAPTISM
    reason = DocumentRequest.RequestReason.PERSONAL
    reason_free = ""
    status = DocumentRequest.Status.SUBMITTED

    # Identité
    requester_last_name = factory.Sequence(lambda n: f"Diallo{n}")
    requester_first_names = factory.Sequence(lambda n: f"Aminata{n}")
    date_of_birth = datetime.date(1990, 1, 1)
    place_of_birth = "Dakar"

    # Contact
    contact_phone = factory.Sequence(lambda n: f"+22177{n:07d}")
    contact_email = factory.Sequence(lambda n: f"contact{n}@example.com")

    # Recherche
    registered_last_name = ""
    registered_first_names = ""
    father_last_name = factory.Sequence(lambda n: f"PereDiallo{n}")
    mother_last_name = factory.Sequence(lambda n: f"MereNdiaye{n}")
    parish_name = factory.Sequence(lambda n: f"Paroisse Test {n}")
    diocese = "Dakar"
    sacrament_approximate_date = "2005"
    sacrament_location = "Dakar"
    additional_info = ""

    document_details = factory.LazyFunction(dict)
    consent_given = True


class ValidFileFactory(DjangoModelFactory):
    """Crée un fichier finalisé (upload_finished_at renseigné) — is_valid == True."""

    class Meta:
        model = File

    original_file_name = factory.Sequence(lambda n: f"document_{n}.pdf")
    file_name = factory.Sequence(lambda n: f"uuid-{n}-document.pdf")
    file_type = "application/pdf"
    uploaded_by = factory.SubFactory(BaseUserFactory)
    upload_finished_at = factory.LazyFunction(timezone.now)


class InvalidFileFactory(DjangoModelFactory):
    """Crée un fichier non finalisé (upload_finished_at absent) — is_valid == False."""

    class Meta:
        model = File

    original_file_name = factory.Sequence(lambda n: f"incomplete_{n}.pdf")
    file_name = factory.Sequence(lambda n: f"uuid-incomplete-{n}.pdf")
    file_type = "application/pdf"
    uploaded_by = factory.SubFactory(BaseUserFactory)
    upload_finished_at = None


class DocumentRequestAttachmentFactory(DjangoModelFactory):
    class Meta:
        model = DocumentRequestAttachment

    request = factory.SubFactory(DocumentRequestFactory)
    file = factory.SubFactory(ValidFileFactory)
    uploaded_by = factory.SubFactory(BaseUserFactory)
    attachment_type = DocumentRequest.AttachmentType.USER_SUPPORTING
    label = "Pièce jointe test"


class InternalNoteFactory(DjangoModelFactory):
    class Meta:
        model = InternalNote

    request = factory.SubFactory(DocumentRequestFactory)
    author = factory.SubFactory(StaffUserFactory)
    content = factory.Sequence(lambda n: f"Note interne numéro {n}")

"""
Factories factory_boy pour les tests du module files.
"""

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.files.models import File
from apps.users.tests.factories import BaseUserFactory


class FileFactory(DjangoModelFactory):
    """Crée un fichier valide (upload terminé) par défaut."""

    class Meta:
        model = File

    original_file_name = factory.Sequence(lambda n: f"document_{n}.pdf")
    file_name = factory.Sequence(lambda n: f"abcdef{n:06d}.pdf")
    file_type = "application/pdf"
    uploaded_by = factory.SubFactory(BaseUserFactory)
    upload_finished_at = factory.LazyFunction(timezone.now)


class PendingFileFactory(DjangoModelFactory):
    """Crée un fichier dont l'upload n'est pas encore terminé (invalide)."""

    class Meta:
        model = File

    original_file_name = factory.Sequence(lambda n: f"pending_{n}.jpg")
    file_name = factory.Sequence(lambda n: f"pending{n:06d}.jpg")
    file_type = "image/jpeg"
    uploaded_by = factory.SubFactory(BaseUserFactory)
    upload_finished_at = None

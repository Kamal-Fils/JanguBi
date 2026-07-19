import mimetypes
import pathlib
from typing import Any, Dict, Tuple

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import ApplicationError
from apps.files.enums import FileUploadStorage
from apps.files.models import File
from apps.files.utils import (
    bytes_to_mib,
    file_generate_local_upload_url,
    file_generate_name,
    file_generate_upload_path,
)
from apps.integrations.aws.client import s3_generate_presigned_post
from apps.users.models import BaseUser


def _validate_file_size(file_obj):
    max_size = settings.FILE_MAX_SIZE

    if file_obj.size > max_size:
        raise ApplicationError(f"Fichier trop volumineux. Taille maximum : {bytes_to_mib(max_size)} MiB.")


def _allowed_extensions() -> set[str]:
    return {ext for extensions in settings.FILE_UPLOAD_ALLOWED_TYPES.values() for ext in extensions}


def validate_file_type(*, file_name: str, file_type: str) -> None:
    """
    Refuse tout fichier hors liste blanche (`FILE_UPLOAD_ALLOWED_TYPES`).

    Le contrôle porte sur TROIS points, car chacun se contourne seul :

    1. l'extension, parce qu'elle détermine le nom stocké et ce que servira S3 ;
    2. le type MIME déclaré, parce qu'il est repris tel quel dans l'URL
       présignée — un client peut annoncer `text/html` pour un `.pdf` et obtenir
       que son fichier soit ensuite servi comme une page ;
    3. la COHÉRENCE entre les deux, sans quoi il suffit de déclarer
       `application/pdf` sur un `.html` pour passer les deux premiers.

    Ces valeurs viennent du client (y compris sur le chemin présigné, où le
    serveur ne voit jamais l'octet uploadé) : elles sont donc à traiter comme
    une saisie utilisateur, pas comme une description fiable du contenu.
    """
    extension = pathlib.Path(file_name or "").suffix.lower()

    if not extension:
        raise ApplicationError("Le nom du fichier doit comporter une extension.")

    if extension not in _allowed_extensions():
        raise ApplicationError(f"Type de fichier non autorisé : « {extension} ».")

    normalized_type = (file_type or "").split(";")[0].strip().lower()

    if not normalized_type:
        raise ApplicationError("Le type du fichier n'a pas pu être déterminé.")

    expected_extensions = settings.FILE_UPLOAD_ALLOWED_TYPES.get(normalized_type)

    if expected_extensions is None:
        raise ApplicationError(f"Type de fichier non autorisé : « {normalized_type} ».")

    if extension not in expected_extensions:
        raise ApplicationError(f"L'extension « {extension} » ne correspond pas au type « {normalized_type} ».")


class FileStandardUploadService:
    """
    This also serves as an example of a service class,
    which encapsulates 2 different behaviors (create & update) under a namespace.

    Meaning, we use the class here for:

    1. The namespace
    2. The ability to reuse `_infer_file_name_and_type` (which can also be an util)
    """

    def __init__(self, user: BaseUser, file_obj):
        self.user = user
        self.file_obj = file_obj

    def _infer_file_name_and_type(self, file_name: str = "", file_type: str = "") -> Tuple[str, str]:
        if not file_name:
            file_name = self.file_obj.name

        if not file_type:
            guessed_file_type, encoding = mimetypes.guess_type(file_name)

            if guessed_file_type is None:
                file_type = ""
            else:
                file_type = guessed_file_type

        return file_name, file_type

    @transaction.atomic
    def create(self, file_name: str = "", file_type: str = "") -> File:
        _validate_file_size(self.file_obj)

        file_name, file_type = self._infer_file_name_and_type(file_name, file_type)
        validate_file_type(file_name=file_name, file_type=file_type)

        obj = File(
            file=self.file_obj,
            original_file_name=file_name,
            file_name=file_generate_name(file_name),
            file_type=file_type,
            uploaded_by=self.user,
            upload_finished_at=timezone.now(),
        )

        obj.full_clean()
        obj.save()

        return obj

    @transaction.atomic
    def update(self, file: File, file_name: str = "", file_type: str = "") -> File:
        _validate_file_size(self.file_obj)

        file_name, file_type = self._infer_file_name_and_type(file_name, file_type)
        validate_file_type(file_name=file_name, file_type=file_type)

        file.file = self.file_obj
        file.original_file_name = file_name
        file.file_name = file_generate_name(file_name)
        file.file_type = file_type
        file.uploaded_by = self.user
        file.upload_finished_at = timezone.now()

        file.full_clean()
        file.save()

        return file


class FileDirectUploadService:
    """
    This also serves as an example of a service class,
    which encapsulates a flow (start & finish) + one-off action (upload_local) into a namespace.

    Meaning, we use the class here for:

    1. The namespace
    """

    def __init__(self, user: BaseUser):
        self.user = user

    @transaction.atomic
    def start(self, *, file_name: str, file_type: str) -> Dict[str, Any]:
        # Chemin le plus exposé : le serveur ne verra JAMAIS l'octet uploadé —
        # le client poste directement sur S3 avec l'URL présignée qu'on lui
        # remet, et le `file_type` ci-dessous est celui qui sera renvoyé plus
        # tard à chaque téléchargement. Valider ici est donc la seule occasion.
        validate_file_type(file_name=file_name, file_type=file_type)

        file = File(
            original_file_name=file_name,
            file_name=file_generate_name(file_name),
            file_type=file_type,
            uploaded_by=self.user,
            file=None,
        )
        file.full_clean()
        file.save()

        upload_path = file_generate_upload_path(file, file.file_name)

        """
        We are doing this in order to have an associated file for the field.
        """
        file.file = file.file.field.attr_class(file, file.file.field, upload_path)
        file.save()

        presigned_data: Dict[str, Any] = {}

        if settings.FILE_UPLOAD_STORAGE == FileUploadStorage.S3:
            presigned_data = s3_generate_presigned_post(file_path=upload_path, file_type=file.file_type)

        else:
            presigned_data = {
                "url": file_generate_local_upload_url(file_id=str(file.id)),
            }

        return {"id": file.id, **presigned_data}

    @transaction.atomic
    def finish(self, *, file: File) -> File:
        # Potentially, check against user
        file.upload_finished_at = timezone.now()
        file.full_clean()
        file.save()

        return file

    @transaction.atomic
    def upload_local(self, *, file: File, file_obj) -> File:
        _validate_file_size(file_obj)

        # Potentially, check against user
        file.file = file_obj
        file.full_clean()
        file.save()

        return file

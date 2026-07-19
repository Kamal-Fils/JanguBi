"""
Tests de la liste blanche des types de fichiers acceptés à l'upload.

Contexte — la faille corrigée : seule la TAILLE était vérifiée. N'importe quel
utilisateur authentifié pouvait déposer un `.html` ou un `.svg`, qui est ensuite
servi depuis MinIO/S3 avec le type déclaré. Un `<script>` dans un SVG servi par
notre domaine, sur un lien d'apparence officielle, est un XSS stocké.

Le chemin présigné (`FileDirectUploadService.start`) est le plus exposé : le
serveur ne voit jamais l'octet uploadé, donc la validation à cet instant est la
seule qui existe.
"""

import pytest

from apps.core.exceptions import ApplicationError
from apps.files.services import validate_file_type


class TestAcceptedFiles:
    """Le périmètre légitime doit continuer de passer, sinon la correction
    casserait le dépôt de pièces justificatives."""

    @pytest.mark.parametrize(
        "file_name,file_type",
        [
            ("acte-de-naissance.pdf", "application/pdf"),
            ("photo.jpg", "image/jpeg"),
            ("photo.jpeg", "image/jpeg"),
            ("avatar.png", "image/png"),
            ("scan.webp", "image/webp"),
            ("photo-iphone.heic", "image/heic"),
            ("homelie.mp3", "audio/mpeg"),
        ],
    )
    def test_legitimate_uploads_are_accepted(self, file_name, file_type):
        validate_file_type(file_name=file_name, file_type=file_type)

    def test_charset_suffix_is_tolerated(self):
        """Les navigateurs ajoutent parfois un paramètre au type ; le refuser
        rejetterait des fichiers parfaitement valides."""
        validate_file_type(file_name="doc.pdf", file_type="application/pdf; charset=binary")

    def test_extension_case_is_ignored(self):
        validate_file_type(file_name="SCAN.PDF", file_type="application/pdf")


class TestRejectedFiles:
    @pytest.mark.parametrize(
        "file_name,file_type",
        [
            ("payload.html", "text/html"),
            ("payload.svg", "image/svg+xml"),
            ("shell.php", "application/x-httpd-php"),
            ("run.exe", "application/octet-stream"),
        ],
    )
    def test_dangerous_types_are_rejected(self, file_name, file_type):
        with pytest.raises(ApplicationError):
            validate_file_type(file_name=file_name, file_type=file_type)

    def test_svg_is_rejected_even_declared_as_an_image(self):
        """Un SVG est un document exécutable déguisé en image : il doit tomber
        même quand le client l'annonce comme une image ordinaire."""
        with pytest.raises(ApplicationError):
            validate_file_type(file_name="logo.svg", file_type="image/png")

    def test_mismatched_extension_and_type_is_rejected(self):
        """Le contournement évident : annoncer un type autorisé sur une
        extension dangereuse. Sans contrôle de cohérence, il passe."""
        with pytest.raises(ApplicationError):
            validate_file_type(file_name="payload.html", file_type="application/pdf")

    def test_allowed_extension_with_dangerous_declared_type_is_rejected(self):
        """Le contournement symétrique : bonne extension, type déclaré
        dangereux — c'est le type qui sera servi au téléchargement."""
        with pytest.raises(ApplicationError):
            validate_file_type(file_name="innocent.pdf", file_type="text/html")

    def test_double_extension_is_judged_on_the_last_one(self):
        with pytest.raises(ApplicationError):
            validate_file_type(file_name="facture.pdf.html", file_type="text/html")

    def test_missing_extension_is_rejected(self):
        with pytest.raises(ApplicationError):
            validate_file_type(file_name="sans_extension", file_type="application/pdf")

    def test_undeterminable_type_is_rejected(self):
        """`_infer_file_name_and_type` renvoie une chaîne vide quand le type
        n'a pas pu être deviné : ce cas ne doit pas passer en silence."""
        with pytest.raises(ApplicationError):
            validate_file_type(file_name="fichier.pdf", file_type="")

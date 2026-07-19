"""Délais (SLA) exposés par l'API et comptages par statut.

Ces deux capacités existent pour que le client n'ait plus à dupliquer les
règles de délai ni à charger le détail de chaque demande. Les tests vérifient
donc aussi ce que le client n'a plus à faire : pas de N+1 sur la liste.
"""

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.documents import sla
from apps.documents.models import DocumentRequest
from apps.documents.selectors import document_request_status_counts
from apps.files.models import File
from apps.users.tests.factories import AdminUserFactory, BaseUserFactory

from .factories import DocumentRequestAttachmentFactory, DocumentRequestFactory

pytestmark = pytest.mark.django_db


def _aged(request_obj, days):
    """Force la date de dernière action — `updated_at` est en auto_now."""
    DocumentRequest.objects.filter(pk=request_obj.pk).update(
        updated_at=timezone.now() - datetime.timedelta(days=days)
    )
    request_obj.refresh_from_db()
    return request_obj


# ---------------------------------------------------------------------------
# Fonctions pures de délai
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (DocumentRequest.Status.SUBMITTED, 7),
        (DocumentRequest.Status.UNDER_VERIFICATION, 7),
        (DocumentRequest.Status.VALIDATED, 3),
        (DocumentRequest.Status.INFO_REQUESTED, 5),
        (DocumentRequest.Status.DOCUMENT_DEPOSITED, None),
        (DocumentRequest.Status.REJECTED, None),
    ],
)
def test_seuil_par_statut_suit_les_reglages_de_l_escalade(status, expected):
    assert sla.sla_threshold_days(status) == expected


def test_anciennete_se_mesure_depuis_la_derniere_action_pas_la_creation():
    # Arrange — créée il y a longtemps mais traitée hier.
    req = DocumentRequestFactory(status=DocumentRequest.Status.UNDER_VERIFICATION)
    DocumentRequest.objects.filter(pk=req.pk).update(
        created_at=timezone.now() - datetime.timedelta(days=30)
    )
    _aged(req, 1)

    # Act / Assert — 1 jour depuis la dernière action, donc pas en retard.
    assert sla.sla_days(req) == 1
    assert sla.is_escalated(req) is False


def test_escalade_au_franchissement_du_seuil():
    req = DocumentRequestFactory(status=DocumentRequest.Status.SUBMITTED)

    assert sla.is_escalated(_aged(req, 6)) is False
    assert sla.is_escalated(_aged(req, 7)) is True


def test_seuil_plus_court_pour_une_demande_validee_en_attente_de_depot():
    req = _aged(DocumentRequestFactory(status=DocumentRequest.Status.VALIDATED), 4)

    # 4 jours dépassent le rappel de dépôt (3 j) alors que le seuil générique (7 j)
    # ne serait pas atteint.
    assert sla.sla_threshold_days(req.status) == 3
    assert sla.is_escalated(req) is True


def test_statut_terminal_sans_delai():
    req = _aged(DocumentRequestFactory(status=DocumentRequest.Status.DOCUMENT_DEPOSITED), 90)

    assert sla.sla_days(req) is None
    assert sla.sla_threshold_days(req.status) is None
    assert sla.is_escalated(req) is False


# ---------------------------------------------------------------------------
# Exposition dans la liste
# ---------------------------------------------------------------------------


def test_liste_expose_delai_et_document_final():
    # Arrange
    admin = AdminUserFactory()
    client = APIClient()
    client.force_authenticate(user=admin)
    req = _aged(DocumentRequestFactory(status=DocumentRequest.Status.SUBMITTED), 9)
    attachment = DocumentRequestAttachmentFactory(
        request=req,
        attachment_type=DocumentRequest.AttachmentType.PARISH_FINAL,
    )
    # Un fichier stocké, sans upload réel : la factory ne renseigne pas le champ
    # fichier, et sans lui l'URL est nulle (même garde que le sérialiseur de
    # pièce jointe existant). On écrit le chemin en base pour éviter de dépendre
    # du service de stockage dans un test unitaire.
    File.objects.filter(pk=attachment.file_id).update(file="documents/acte.pdf")

    # Act
    response = client.get(reverse("api:documents:admin-document-request-list"))

    # Assert
    assert response.status_code == 200
    row = next(r for r in response.data["results"] if r["id"] == str(req.id))
    assert row["sla_days"] == 9
    assert row["sla_threshold_days"] == 7
    assert row["is_escalated"] is True
    assert row["final_document_url"]


def test_liste_sans_document_final_renvoie_null():
    admin = AdminUserFactory()
    client = APIClient()
    client.force_authenticate(user=admin)
    req = DocumentRequestFactory()
    # Une pièce du fidèle ne doit pas être confondue avec le document final.
    DocumentRequestAttachmentFactory(
        request=req,
        attachment_type=DocumentRequest.AttachmentType.USER_SUPPORTING,
    )

    response = client.get(reverse("api:documents:admin-document-request-list"))

    row = next(r for r in response.data["results"] if r["id"] == str(req.id))
    assert row["final_document_url"] is None


def test_liste_ne_fait_pas_de_requete_par_demande(django_assert_max_num_queries):
    """Le lien du document final ne doit pas coûter une requête par ligne."""
    admin = AdminUserFactory()
    client = APIClient()
    client.force_authenticate(user=admin)
    for _ in range(5):
        req = DocumentRequestFactory()
        DocumentRequestAttachmentFactory(
            request=req,
            attachment_type=DocumentRequest.AttachmentType.PARISH_FINAL,
        )

    url = reverse("api:documents:admin-document-request-list")
    # Auth + scoping + count + page + prefetch : borne large, mais qui explose
    # immédiatement si le prefetch des pièces jointes disparaît (5 requêtes de plus).
    with django_assert_max_num_queries(12):
        response = client.get(url)

    assert response.status_code == 200
    assert len(response.data["results"]) == 5


# ---------------------------------------------------------------------------
# Comptages par statut
# ---------------------------------------------------------------------------


def test_comptages_renvoient_toujours_les_six_statuts():
    admin = AdminUserFactory()
    DocumentRequestFactory(status=DocumentRequest.Status.SUBMITTED)
    DocumentRequestFactory(status=DocumentRequest.Status.SUBMITTED)
    DocumentRequestFactory(status=DocumentRequest.Status.REJECTED)

    data = document_request_status_counts(user=admin)

    assert set(data["counts"]) == {s.value for s in DocumentRequest.Status}
    assert data["counts"]["submitted"] == 2
    assert data["counts"]["rejected"] == 1
    assert data["counts"]["validated"] == 0
    assert data["total"] == 3


def test_comptages_ignorent_le_filtre_statut():
    """Sinon les autres statuts seraient comptés à zéro alors qu'ils existent."""
    admin = AdminUserFactory()
    DocumentRequestFactory(status=DocumentRequest.Status.SUBMITTED)
    DocumentRequestFactory(status=DocumentRequest.Status.REJECTED)

    data = document_request_status_counts(user=admin, filters={"status": "submitted"})

    assert data["counts"]["rejected"] == 1
    assert data["total"] == 2


def test_comptages_honorent_les_autres_filtres():
    admin = AdminUserFactory()
    DocumentRequestFactory(document_type=DocumentRequest.DocumentType.BAPTISM)
    DocumentRequestFactory(document_type=DocumentRequest.DocumentType.CONFIRMATION)

    data = document_request_status_counts(
        user=admin, filters={"document_type": "baptism"}
    )

    assert data["total"] == 1


def test_endpoint_comptages_refuse_un_non_admin():
    client = APIClient()
    client.force_authenticate(user=BaseUserFactory())

    response = client.get(reverse("api:documents:admin-document-request-counts"))

    assert response.status_code == 403


def test_endpoint_comptages_renvoie_la_forme_attendue():
    client = APIClient()
    client.force_authenticate(user=AdminUserFactory())
    DocumentRequestFactory(status=DocumentRequest.Status.SUBMITTED)

    response = client.get(reverse("api:documents:admin-document-request-counts"))

    assert response.status_code == 200
    assert response.data["total"] == 1
    assert response.data["counts"]["submitted"] == 1
    assert response.data["counts"]["document_deposited"] == 0

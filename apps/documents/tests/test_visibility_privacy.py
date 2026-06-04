"""
Chantier 4 — confidentialité du cloisonnement des demandes de document.

DÉCISION : visibilité d'une demande = admins de la paroisse CIBLE (target_parish)
uniquement + le demandeur. Le curé de la paroisse HOME du demandeur ne doit PAS voir
une demande dont la cible est une AUTRE paroisse (exposition PII inter-paroisse), ni
en liste, ni en detail/actions. Repli legacy : si target_parish est NULL (demande
orpheline), la paroisse principale du demandeur fait foi.
"""

from unittest.mock import patch

import pytest
from django.http import Http404

from apps.documents.selectors import document_request_get_for_admin, document_request_list
from apps.documents.models import DocumentRequest
from apps.documents.services import document_request_create
from apps.org.tests.factories import ParishFactory
from apps.users.enums import RoleScope, UserRole
from apps.users.models import RoleAssignment
from apps.users.tests.factories import BaseUserFactory, ProfileFactory

from .factories import DocumentRequestFactory

_NO_COMMIT = "apps.documents.services.transaction.on_commit"


def _data(**extra):
    return {
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
        "diocese": "Diocèse texte",
        "sacrament_approximate_date": "2005",
        "sacrament_location": "Dakar",
        "consent_given": True,
        **extra,
    }


def _cure(parish, email):
    user = BaseUserFactory(email=email, role=UserRole.PARISH_ADMIN)
    RoleAssignment.objects.create(
        user=user, role=UserRole.PARISH_ADMIN, scope=RoleScope.PARISH,
        parish=parish, is_active=True,
    )
    return user


def _in_list(user, req):
    return req.id in set(document_request_list(user=user).values_list("id", flat=True))


@pytest.mark.django_db
def test_document_request_to_C_not_visible_to_home_parish_curate():
    # Demandeur dont la paroisse HOME est A ; demande explicitement adressée à C.
    parish_a, parish_c = ParishFactory(), ParishFactory()
    requester = BaseUserFactory()
    ProfileFactory(user=requester, primary_parish=parish_a)  # home = A

    with patch(_NO_COMMIT):
        req = document_request_create(requester=requester, data=_data(parish_id=parish_c.id))
    assert req.target_parish_id == parish_c.id

    cure_a = _cure(parish_a, "cure_home_a@test.com")
    # LISTE : invisible au curé de la paroisse home.
    assert not _in_list(cure_a, req)
    # DETAIL/ACTIONS : 404 pour le curé de la paroisse home.
    with pytest.raises(Http404):
        document_request_get_for_admin(request_id=req.id, user=cure_a)


@pytest.mark.django_db
def test_document_request_visible_to_target_parish_curate():
    parish_a, parish_c = ParishFactory(), ParishFactory()
    requester = BaseUserFactory()
    ProfileFactory(user=requester, primary_parish=parish_a)

    with patch(_NO_COMMIT):
        req = document_request_create(requester=requester, data=_data(parish_id=parish_c.id))

    cure_c = _cure(parish_c, "cure_target_c@test.com")
    assert _in_list(cure_c, req)
    assert document_request_get_for_admin(request_id=req.id, user=cure_c).id == req.id


@pytest.mark.django_db
def test_document_request_always_visible_to_requester():
    # NON-RÉGRESSION : le demandeur voit toujours sa propre demande.
    parish_a, parish_c = ParishFactory(), ParishFactory()
    requester = BaseUserFactory()
    ProfileFactory(user=requester, primary_parish=parish_a)

    with patch(_NO_COMMIT):
        req = document_request_create(requester=requester, data=_data(parish_id=parish_c.id))

    assert _in_list(requester, req)


@pytest.mark.django_db
def test_orphan_document_still_visible_to_home_parish_curate():
    # Repli legacy : sans target_parish (orpheline), la paroisse principale fait foi.
    parish_a = ParishFactory()
    requester = BaseUserFactory()
    ProfileFactory(user=requester, primary_parish=parish_a)

    # B5c ne produit plus d'orphelines (parish_id requis) → on construit l'orpheline
    # legacy directement via la factory (target_parish NULL).
    req = DocumentRequestFactory(requester=requester, target_parish=None)
    assert req.target_parish_id is None

    cure_a = _cure(parish_a, "cure_orphan_a@test.com")
    assert _in_list(cure_a, req)  # repli sur primary_parish du demandeur

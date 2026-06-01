"""
Chantier 4 — la paroisse de REGISTRE peut être N'IMPORTE QUELLE paroisse.

Le demandeur cible une paroisse explicite (le registre du sacrement) sans y être
membre/admin ; diocèse dérivé du FK ; ambiguïté (>1 appartenance) → choix explicite
exigé ; recherche de paroisses sur TOUTES les paroisses (nom + ville). Non-régression
A5 + chemin legacy.
"""

from unittest.mock import patch

import pytest

from apps.core.exceptions import ApplicationError
from apps.documents.models import DocumentRequest
from apps.documents.selectors import document_request_list
from apps.documents.services import document_request_create
from apps.org.selectors import parish_list
from apps.org.tests.factories import ChurchFactory, ParishFactory
from apps.users.enums import RoleScope, UserRole
from apps.users.models import RoleAssignment
from apps.users.services_memberships import membership_create
from apps.users.tests.factories import BaseUserFactory, ProfileFactory

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
        "parish_name": "Saint-Pierre (texte legacy)",
        "diocese": "Diocèse texte legacy",
        "sacrament_approximate_date": "2005",
        "sacrament_location": "Dakar",
        "consent_given": True,
        **extra,
    }


def _requester_with_memberships(*parishes):
    user = BaseUserFactory()
    for i, parish in enumerate(parishes):
        church = ChurchFactory(parish=parish)
        membership_create(user=user, church=church, is_primary=(i == 0))
    user.refresh_from_db()
    return user


def _cure(parish, email):
    user = BaseUserFactory(email=email, role=UserRole.PARISH_ADMIN)
    RoleAssignment.objects.create(
        user=user, role=UserRole.PARISH_ADMIN, scope=RoleScope.PARISH,
        parish=parish, is_active=True,
    )
    return user


@pytest.mark.django_db
def test_document_target_can_be_any_parish():
    # Demandeur membre de A & B ; demande adressée à C (paroisse NON-membre).
    parish_a, parish_b, parish_c = ParishFactory(), ParishFactory(), ParishFactory()
    requester = _requester_with_memberships(parish_a, parish_b)

    with patch(_NO_COMMIT):
        req = document_request_create(requester=requester, data=_data(parish_id=parish_c.id))

    assert req.target_parish_id == parish_c.id

    # Routage : le curé de C voit la demande dans sa liste.
    cure_c = _cure(parish_c, "cure_c@test.com")
    assert req.id in set(document_request_list(user=cure_c).values_list("id", flat=True))


@pytest.mark.django_db
def test_document_request_to_parish_C_not_visible_to_curate_of_membership_parish():
    # Cloisonnement : une demande explicitement routée vers C n'apparaît PAS chez le
    # curé d'une paroisse d'appartenance NON principale (B) ni d'une paroisse tierce (D).
    parish_a, parish_b, parish_c, parish_d = (
        ParishFactory(), ParishFactory(), ParishFactory(), ParishFactory()
    )
    requester = _requester_with_memberships(parish_a, parish_b)  # primaire = A

    with patch(_NO_COMMIT):
        req = document_request_create(requester=requester, data=_data(parish_id=parish_c.id))

    cure_b = _cure(parish_b, "cure_b@test.com")
    cure_d = _cure(parish_d, "cure_d@test.com")
    assert req.id not in set(document_request_list(user=cure_b).values_list("id", flat=True))
    assert req.id not in set(document_request_list(user=cure_d).values_list("id", flat=True))


@pytest.mark.django_db
def test_document_diocese_derived_from_target_parish():
    # FK présente → diocèse = diocèse du FK, PAS le texte d'entrée.
    parish = ParishFactory()
    requester = _requester_with_memberships(parish)

    with patch(_NO_COMMIT):
        req = document_request_create(
            requester=requester,
            data=_data(parish_id=parish.id, diocese="Diocèse BIDON texte"),
        )

    assert req.diocese == parish.diocese.name
    assert req.diocese != "Diocèse BIDON texte"
    # parish_name (texte legacy) reste lisible.
    assert req.parish_name == "Saint-Pierre (texte legacy)"


@pytest.mark.django_db
def test_document_requires_explicit_parish_when_multiple_memberships():
    # >1 appartenance + pas de parish_id → erreur claire (pas de repli silencieux).
    requester = _requester_with_memberships(ParishFactory(), ParishFactory())

    with patch(_NO_COMMIT):
        with pytest.raises(ApplicationError, match="plusieurs paroisses"):
            document_request_create(requester=requester, data=_data())  # sans parish_id


# ---------------------------------------------------------------------------
# Recherche de paroisses (picker)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_parish_search_returns_any_parish_by_name_and_city():
    p_dakar = ParishFactory(name="Saint-Joseph", city="Dakar")
    p_thies = ParishFactory(name="Sainte-Anne", city="Thiès")
    ParishFactory(name="Saint-Paul", city="Saint-Louis")

    # Recherche par nom (toutes paroisses, aucun scoping).
    by_name = set(parish_list(search="Sainte-Anne").values_list("id", flat=True))
    assert by_name == {p_thies.id}

    # Param ville dédié.
    by_city = set(parish_list(city="Dakar").values_list("id", flat=True))
    assert by_city == {p_dakar.id}


# ---------------------------------------------------------------------------
# NON-RÉGRESSION
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_legacy_single_membership_without_parish_id_still_works():
    # 1 appartenance, pas de parish_id → défaut de transition = paroisse principale.
    parish = ParishFactory()
    requester = _requester_with_memberships(parish)

    with patch(_NO_COMMIT):
        req = document_request_create(requester=requester, data=_data())  # sans parish_id

    assert req.target_parish_id == parish.id


@pytest.mark.django_db
def test_a5_invalid_parish_id_still_raises():
    requester = _requester_with_memberships(ParishFactory())
    with patch(_NO_COMMIT):
        with pytest.raises(ApplicationError, match="introuvable"):
            document_request_create(requester=requester, data=_data(parish_id=999999))


@pytest.mark.django_db
def test_a5_no_resolved_parish_still_rejected():
    # 0 appartenance, pas de parish_id, pas de paroisse principale → rejet orphelin.
    requester = BaseUserFactory()  # aucun profil/appartenance
    with patch(_NO_COMMIT):
        with pytest.raises(ApplicationError):
            document_request_create(requester=requester, data=_data())

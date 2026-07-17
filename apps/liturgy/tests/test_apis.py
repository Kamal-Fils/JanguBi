"""
API tests — accès à la liturgie du jour.

Contrat : les LECTURES DE MESSE sont accessibles à tout utilisateur connecté
(onglet « Aujourd'hui » du fidèle) ; les OFFICES (Liturgie des Heures) sont
réservés au clergé/religieux et strippés du payload pour les autres.
"""

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.users.tests.factories import BaseUserFactory

from .factories import LiturgicalDateFactory, OfficeFactory, ReadingFactory


def _today_date_obj():
    date_obj = LiturgicalDateFactory(date=timezone.localtime().date(), zone="afrique")
    ReadingFactory(liturgical_date=date_obj, type="lecture_1")
    OfficeFactory(liturgical_date=date_obj, office_type="laudes")
    return date_obj


def _client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_liturgy_today_requires_authentication():
    response = APIClient().get(reverse("api:liturgy:today"))
    assert response.status_code == 401


@pytest.mark.django_db
def test_liturgy_today_returns_readings_without_offices_for_fidele():
    # Arrange
    _today_date_obj()
    client = _client_for(BaseUserFactory())  # fidèle (pastoral_role vide)

    # Act
    response = client.get(reverse("api:liturgy:today"))

    # Assert — les lectures passent, les offices sont strippés
    assert response.status_code == 200
    assert len(response.data["readings"]) >= 1
    assert response.data["offices"] == []


@pytest.mark.django_db
def test_liturgy_today_includes_offices_for_clergy():
    # Arrange
    _today_date_obj()
    client = _client_for(BaseUserFactory(pastoral_role="pretre"))

    # Act
    response = client.get(reverse("api:liturgy:today"))

    # Assert
    assert response.status_code == 200
    assert len(response.data["offices"]) >= 1


@pytest.mark.django_db
def test_office_endpoint_still_forbidden_for_fidele():
    # Les endpoints d'office dédiés restent gatés clergé.
    _today_date_obj()
    client = _client_for(BaseUserFactory())
    response = client.get(reverse("api:liturgy:v1-laudes"))
    assert response.status_code == 403

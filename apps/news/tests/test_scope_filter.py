"""
Chantier news-scope-filters — filtre serveur ?scope_type=&scope_id= sur /news/feed/,
BORNÉ aux appartenances de l'utilisateur (ne rouvre pas le cloisonnement).
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.org.tests.factories import ChurchFactory
from apps.users.services_memberships import membership_create
from apps.users.tests.factories import BaseUserFactory

from .factories import (
    PublishedArticleFactory,
    PublishedChurchArticleFactory,
    PublishedDioceseArticleFactory,
    PublishedParishArticleFactory,
)

FEED_URL = reverse("api:news:feed")


@pytest.fixture
def aminata():
    """Fidèle multi-appartenance : 2 églises → 2 paroisses → 2 diocèses."""
    church_a = ChurchFactory()
    church_b = ChurchFactory()
    user = BaseUserFactory()
    membership_create(user=user, church=church_a, is_primary=True)
    membership_create(user=user, church=church_b)
    client = APIClient()
    client.force_authenticate(user=user)
    client._user = user
    client._church_a = church_a
    client._church_b = church_b
    return client


def _ids(resp):
    # L'id article est un UUID sérialisé en str dans la réponse → on compare en str.
    return {str(a["id"]) for a in resp.data["results"]}


@pytest.mark.django_db
def test_feed_filter_church_returns_only_that_church(aminata):
    art_a = PublishedChurchArticleFactory(scope_church=aminata._church_a)
    art_b = PublishedChurchArticleFactory(scope_church=aminata._church_b)
    art_global = PublishedArticleFactory()

    resp = aminata.get(FEED_URL, {"scope_type": "church", "scope_id": aminata._church_a.id})

    assert resp.status_code == 200
    assert _ids(resp) == {str(art_a.id)}
    assert str(art_b.id) not in _ids(resp)
    assert str(art_global.id) not in _ids(resp)


@pytest.mark.django_db
def test_feed_filter_global_returns_only_global(aminata):
    art_global = PublishedArticleFactory()
    PublishedChurchArticleFactory(scope_church=aminata._church_a)
    PublishedParishArticleFactory(scope_parish=aminata._church_a.parish)
    PublishedDioceseArticleFactory(scope_diocese=aminata._church_a.parish.diocese)

    resp = aminata.get(FEED_URL, {"scope_type": "global"})

    assert resp.status_code == 200
    assert _ids(resp) == {str(art_global.id)}


@pytest.mark.django_db
def test_feed_no_filter_returns_aggregate(aminata):
    art_a = PublishedChurchArticleFactory(scope_church=aminata._church_a)
    art_b = PublishedChurchArticleFactory(scope_church=aminata._church_b)
    art_global = PublishedArticleFactory()

    resp = aminata.get(FEED_URL)

    assert resp.status_code == 200
    assert {str(art_a.id), str(art_b.id), str(art_global.id)} <= _ids(resp)


@pytest.mark.django_db
def test_feed_filter_church_outside_memberships_returns_403(aminata):
    # Une église dont Aminata n'est PAS membre → refusée par le serveur (403).
    foreign_church = ChurchFactory()
    PublishedChurchArticleFactory(scope_church=foreign_church)

    resp = aminata.get(
        FEED_URL, {"scope_type": "church", "scope_id": foreign_church.id}
    )

    assert resp.status_code == 403


@pytest.mark.django_db
def test_feed_filter_invalid_scope_type_returns_400(aminata):
    resp = aminata.get(FEED_URL, {"scope_type": "planet", "scope_id": 1})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_feed_filter_territorial_scope_without_id_returns_400(aminata):
    resp = aminata.get(FEED_URL, {"scope_type": "church"})
    assert resp.status_code == 400

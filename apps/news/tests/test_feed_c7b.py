"""
Chantier 7b (back) — endpoint du fil d'actualités AGRÉGÉ.

GET /news/feed/ expose article_list_for_user (global ∪ église ∪ paroisse ∪ diocèse,
agrégé au C3a). Prérequis du fil unique côté front (suppression des onglets).
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.org.tests.factories import ChurchFactory, ParishFactory
from apps.users.services_memberships import membership_create
from apps.users.tests.factories import BaseUserFactory

from .factories import (
    PublishedArticleFactory,
    PublishedChurchArticleFactory,
    PublishedDioceseArticleFactory,
    PublishedParishArticleFactory,
)


def _member(church):
    user = BaseUserFactory()
    membership_create(user=user, church=church, is_primary=True)
    return user


@pytest.mark.django_db
def test_news_feed_requires_auth():
    resp = APIClient().get(reverse("api:news:feed"))
    assert resp.status_code == 401


@pytest.mark.django_db
def test_news_feed_aggregates_user_scopes():
    church = ChurchFactory()
    parish = church.parish
    diocese = parish.diocese
    user = _member(church)

    g = PublishedArticleFactory()  # global
    c = PublishedChurchArticleFactory(scope_church=church)
    p = PublishedParishArticleFactory(scope_parish=parish)
    d = PublishedDioceseArticleFactory(scope_diocese=diocese)
    other = PublishedParishArticleFactory(scope_parish=ParishFactory())

    client = APIClient()
    client.force_authenticate(user)
    resp = client.get(reverse("api:news:feed"))

    assert resp.status_code == 200
    ids = {a["id"] for a in resp.data["results"]}
    assert {str(g.id), str(c.id), str(p.id), str(d.id)} <= ids
    assert str(other.id) not in ids

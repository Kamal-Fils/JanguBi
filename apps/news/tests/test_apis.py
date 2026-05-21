"""
Tests des APIs apps/news.
Couvre : endpoints publics, endpoints admin (CRUD, publish, unpublish, delete).
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.news.models import Article
from apps.users.tests.factories import BaseUserFactory, StaffUserFactory

from .factories import (
    ArticleCategoryFactory,
    ArticleFactory,
    PublishedArticleFactory,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def anon_client():
    return APIClient()


@pytest.fixture
def auth_client():
    client = APIClient()
    user = BaseUserFactory()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def admin_client():
    client = APIClient()
    user = StaffUserFactory()
    client.force_authenticate(user=user)
    client._user = user
    return client


# ---------------------------------------------------------------------------
# CategoryListApi — GET /news/categories/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_category_list_returns_200_for_anonymous():
    # Arrange
    ArticleCategoryFactory(is_active=True)
    ArticleCategoryFactory(is_active=False)
    url = reverse("api:news:category-list")

    # Act
    response = APIClient().get(url)

    # Assert
    assert response.status_code == 200
    assert len(response.data) == 1


# ---------------------------------------------------------------------------
# ArticleGlobalListApi — GET /news/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_global_list_returns_200_for_anonymous():
    # Arrange
    PublishedArticleFactory()
    url = reverse("api:news:global-list")

    # Act
    response = APIClient().get(url)

    # Assert
    assert response.status_code == 200
    assert response.data["count"] == 1


@pytest.mark.django_db
def test_global_list_excludes_drafts():
    # Arrange
    ArticleFactory(status=Article.Status.DRAFT)
    url = reverse("api:news:global-list")

    # Act
    response = APIClient().get(url)

    # Assert
    assert response.status_code == 200
    assert response.data["count"] == 0


# ---------------------------------------------------------------------------
# ArticleDetailApi — GET /news/<uuid>/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_article_detail_returns_200_for_published():
    # Arrange
    article = PublishedArticleFactory()
    url = reverse("api:news:detail", kwargs={"article_id": article.id})

    # Act
    response = APIClient().get(url)

    # Assert
    assert response.status_code == 200
    assert str(response.data["id"]) == str(article.id)


@pytest.mark.django_db
def test_article_detail_returns_404_for_draft():
    # Arrange
    article = ArticleFactory(status=Article.Status.DRAFT)
    url = reverse("api:news:detail", kwargs={"article_id": article.id})

    # Act
    response = APIClient().get(url)

    # Assert
    assert response.status_code == 404


@pytest.mark.django_db
def test_article_detail_returns_404_for_unknown_uuid():
    # Arrange
    url = reverse("api:news:detail", kwargs={"article_id": "00000000-0000-0000-0000-000000000000"})

    # Act
    response = APIClient().get(url)

    # Assert
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# ArticleParishListApi — GET /news/parish/<id>/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_parish_list_requires_auth(anon_client):
    # Arrange
    url = reverse("api:news:parish-list", kwargs={"parish_id": 1})

    # Act
    response = anon_client.get(url)

    # Assert
    assert response.status_code == 401


@pytest.mark.django_db
def test_parish_list_returns_200_for_authenticated(auth_client):
    # Arrange
    url = reverse("api:news:parish-list", kwargs={"parish_id": 1})

    # Act
    response = auth_client.get(url)

    # Assert
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# ArticleDioceseListApi — GET /news/diocese/<id>/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_diocese_list_requires_auth(anon_client):
    # Arrange
    url = reverse("api:news:diocese-list", kwargs={"diocese_id": 1})

    # Act
    response = anon_client.get(url)

    # Assert
    assert response.status_code == 401


@pytest.mark.django_db
def test_diocese_list_returns_200_for_authenticated(auth_client):
    # Arrange
    url = reverse("api:news:diocese-list", kwargs={"diocese_id": 1})

    # Act
    response = auth_client.get(url)

    # Assert
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# AdminArticleListApi — GET /news/admin/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_list_requires_auth(anon_client):
    # Arrange
    url = reverse("api:news:admin-list")

    # Act
    response = anon_client.get(url)

    # Assert
    assert response.status_code == 401


@pytest.mark.django_db
def test_admin_list_requires_staff(auth_client):
    # Arrange
    url = reverse("api:news:admin-list")

    # Act
    response = auth_client.get(url)

    # Assert
    assert response.status_code == 403


@pytest.mark.django_db
def test_admin_list_returns_200_for_staff(admin_client):
    # Arrange
    ArticleFactory()
    url = reverse("api:news:admin-list")

    # Act
    response = admin_client.get(url)

    # Assert
    assert response.status_code == 200
    assert response.data["count"] == 1


# ---------------------------------------------------------------------------
# AdminArticleCreateApi — POST /news/admin/create/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_create_returns_201(admin_client):
    # Arrange
    category = ArticleCategoryFactory()
    url = reverse("api:news:admin-create")
    payload = {
        "title": "Nouvelle paroissiale",
        "content": "Contenu de l'article.",
        "category_id": category.id,
    }

    # Act
    response = admin_client.post(url, payload, format="json")

    # Assert
    assert response.status_code == 201
    assert response.data["title"] == "Nouvelle paroissiale"
    assert response.data["status"] == Article.Status.DRAFT


@pytest.mark.django_db
def test_admin_create_requires_auth(anon_client):
    # Arrange
    url = reverse("api:news:admin-create")

    # Act
    response = anon_client.post(url, {}, format="json")

    # Assert
    assert response.status_code == 401


@pytest.mark.django_db
def test_admin_create_returns_400_for_inactive_category(admin_client):
    # Arrange
    category = ArticleCategoryFactory(is_active=False)
    url = reverse("api:news:admin-create")
    payload = {
        "title": "Test",
        "content": "Contenu.",
        "category_id": category.id,
    }

    # Act
    response = admin_client.post(url, payload, format="json")

    # Assert
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# AdminArticleUpdateApi — PATCH /news/admin/<uuid>/update/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_update_returns_200(admin_client):
    # Arrange
    article = ArticleFactory()
    url = reverse("api:news:admin-update", kwargs={"article_id": article.id})
    payload = {"title": "Titre modifié"}

    # Act
    response = admin_client.patch(url, payload, format="json")

    # Assert
    assert response.status_code == 200
    assert response.data["title"] == "Titre modifié"


@pytest.mark.django_db
def test_admin_update_returns_400_for_unpublished_article(admin_client):
    # Arrange
    article = ArticleFactory(status=Article.Status.UNPUBLISHED)
    url = reverse("api:news:admin-update", kwargs={"article_id": article.id})

    # Act
    response = admin_client.patch(url, {"title": "Test"}, format="json")

    # Assert
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# AdminArticlePublishApi — POST /news/admin/<uuid>/publish/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_publish_returns_200(admin_client):
    # Arrange
    article = ArticleFactory()
    url = reverse("api:news:admin-publish", kwargs={"article_id": article.id})

    # Act
    response = admin_client.post(url)

    # Assert
    assert response.status_code == 200
    assert response.data["status"] == Article.Status.PUBLISHED


@pytest.mark.django_db
def test_admin_publish_returns_400_if_already_published(admin_client):
    # Arrange
    article = PublishedArticleFactory()
    url = reverse("api:news:admin-publish", kwargs={"article_id": article.id})

    # Act
    response = admin_client.post(url)

    # Assert
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# AdminArticleUnpublishApi — POST /news/admin/<uuid>/unpublish/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_unpublish_returns_200(admin_client):
    # Arrange
    article = PublishedArticleFactory()
    url = reverse("api:news:admin-unpublish", kwargs={"article_id": article.id})

    # Act
    response = admin_client.post(url, {"reason": "Contenu obsolète."}, format="json")

    # Assert
    assert response.status_code == 200
    assert response.data["status"] == Article.Status.UNPUBLISHED


@pytest.mark.django_db
def test_admin_unpublish_returns_400_if_not_published(admin_client):
    # Arrange
    article = ArticleFactory(status=Article.Status.DRAFT)
    url = reverse("api:news:admin-unpublish", kwargs={"article_id": article.id})

    # Act
    response = admin_client.post(url, {}, format="json")

    # Assert
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# AdminArticleDeleteApi — DELETE /news/admin/<uuid>/delete/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_delete_draft_returns_204(admin_client):
    # Arrange
    article = ArticleFactory()
    url = reverse("api:news:admin-delete", kwargs={"article_id": article.id})

    # Act
    response = admin_client.delete(url)

    # Assert
    assert response.status_code == 204
    assert not Article.objects.filter(pk=article.pk).exists()


@pytest.mark.django_db
def test_admin_delete_published_returns_400(admin_client):
    # Arrange
    article = PublishedArticleFactory()
    url = reverse("api:news:admin-delete", kwargs={"article_id": article.id})

    # Act
    response = admin_client.delete(url)

    # Assert
    assert response.status_code == 400


@pytest.mark.django_db
def test_admin_delete_requires_auth(anon_client):
    # Arrange
    article = ArticleFactory()
    url = reverse("api:news:admin-delete", kwargs={"article_id": article.id})

    # Act
    response = anon_client.delete(url)

    # Assert
    assert response.status_code == 401

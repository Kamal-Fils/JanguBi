"""
Tests des selectors apps/news.
Couvre : category_list, article_list, article_list_global,
         article_list_for_parish, article_list_for_diocese,
         article_get, article_get_by_slug.
"""

import pytest

from apps.org.tests.factories import DioceseFactory, ParishFactory
from apps.news.models import Article
from apps.news.selectors import (
    article_get,
    article_get_by_slug,
    article_list,
    article_list_for_diocese,
    article_list_for_parish,
    article_list_global,
    category_list,
)

from .factories import (
    ArticleCategoryFactory,
    ArticleFactory,
    DioceseArticleFactory,
    ParishArticleFactory,
    PublishedArticleFactory,
    PublishedDioceseArticleFactory,
    PublishedParishArticleFactory,
)


# ---------------------------------------------------------------------------
# category_list
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_category_list_returns_active_only_by_default():
    # Arrange
    ArticleCategoryFactory(is_active=True)
    ArticleCategoryFactory(is_active=True)
    ArticleCategoryFactory(is_active=False)

    # Act
    result = category_list()

    # Assert
    assert result.count() == 2
    assert all(c.is_active for c in result)


@pytest.mark.django_db
def test_category_list_returns_all_when_active_only_false():
    # Arrange
    ArticleCategoryFactory(is_active=True)
    ArticleCategoryFactory(is_active=False)

    # Act
    result = category_list(active_only=False)

    # Assert
    assert result.count() == 2


@pytest.mark.django_db
def test_category_list_ordered_by_display_order():
    # Arrange
    cat_b = ArticleCategoryFactory(display_order=2)
    cat_a = ArticleCategoryFactory(display_order=1)

    # Act
    result = list(category_list())

    # Assert
    assert result[0].id == cat_a.id
    assert result[1].id == cat_b.id


# ---------------------------------------------------------------------------
# article_list
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_article_list_returns_published_by_default():
    # Arrange
    PublishedArticleFactory()
    ArticleFactory(status=Article.Status.DRAFT)

    # Act
    result = article_list()

    # Assert
    assert result.count() == 1
    assert result.first().status == Article.Status.PUBLISHED


@pytest.mark.django_db
def test_article_list_filter_by_status_draft():
    # Arrange
    ArticleFactory(status=Article.Status.DRAFT)
    PublishedArticleFactory()

    # Act
    result = article_list(status=Article.Status.DRAFT)

    # Assert
    assert result.count() == 1
    assert result.first().status == Article.Status.DRAFT


@pytest.mark.django_db
def test_article_list_filter_by_scope_type():
    # Arrange
    PublishedArticleFactory()
    PublishedParishArticleFactory()

    # Act
    result = article_list(scope_type=Article.ScopeType.PARISH)

    # Assert
    assert result.count() == 1
    assert result.first().scope_type == Article.ScopeType.PARISH


@pytest.mark.django_db
def test_article_list_filter_by_category_slug():
    # Arrange
    cat = ArticleCategoryFactory()
    other_cat = ArticleCategoryFactory()
    PublishedArticleFactory(category=cat)
    PublishedArticleFactory(category=other_cat)

    # Act
    result = article_list(category_slug=cat.slug)

    # Assert
    assert result.count() == 1
    assert result.first().category_id == cat.id


@pytest.mark.django_db
def test_article_list_filter_by_search():
    # Arrange
    PublishedArticleFactory(title="Messe de Noël")
    PublishedArticleFactory(title="Retraite spirituelle")

    # Act
    result = article_list(search="Noël")

    # Assert
    assert result.count() == 1
    assert "Noël" in result.first().title


@pytest.mark.django_db
def test_article_list_empty_status_returns_all():
    # Arrange
    PublishedArticleFactory()
    ArticleFactory(status=Article.Status.DRAFT)

    # Act
    result = article_list(status="")

    # Assert
    assert result.count() == 2


# ---------------------------------------------------------------------------
# article_list_global
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_article_list_global_returns_only_published_global():
    # Arrange
    PublishedArticleFactory()
    PublishedParishArticleFactory()
    ArticleFactory(status=Article.Status.DRAFT)

    # Act
    result = article_list_global()

    # Assert
    assert result.count() == 1
    assert result.first().scope_type == Article.ScopeType.GLOBAL


@pytest.mark.django_db
def test_article_list_global_filtered_by_search():
    # Arrange
    PublishedArticleFactory(title="Annonce importante")
    PublishedArticleFactory(title="Autre article")

    # Act
    result = article_list_global(search="importante")

    # Assert
    assert result.count() == 1


# ---------------------------------------------------------------------------
# article_list_for_parish
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_article_list_for_parish_returns_only_matching_parish():
    # Arrange
    parish_a = ParishFactory()
    parish_b = ParishFactory()
    PublishedParishArticleFactory(scope_parish=parish_a)
    PublishedParishArticleFactory(scope_parish=parish_b)
    PublishedArticleFactory()

    # Act
    result = article_list_for_parish(parish_id=parish_a.id)

    # Assert
    assert result.count() == 1
    assert result.first().scope_parish_id == parish_a.id


@pytest.mark.django_db
def test_article_list_for_parish_only_published():
    # Arrange
    parish = ParishFactory()
    ParishArticleFactory(scope_parish=parish, status=Article.Status.DRAFT)
    PublishedParishArticleFactory(scope_parish=parish)

    # Act
    result = article_list_for_parish(parish_id=parish.id)

    # Assert
    assert result.count() == 1
    assert result.first().status == Article.Status.PUBLISHED


# ---------------------------------------------------------------------------
# article_list_for_diocese
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_article_list_for_diocese_returns_only_matching_diocese():
    # Arrange
    diocese_a = DioceseFactory()
    diocese_b = DioceseFactory()
    PublishedDioceseArticleFactory(scope_diocese=diocese_a)
    PublishedDioceseArticleFactory(scope_diocese=diocese_b)
    PublishedArticleFactory()

    # Act
    result = article_list_for_diocese(diocese_id=diocese_a.id)

    # Assert
    assert result.count() == 1
    assert result.first().scope_diocese_id == diocese_a.id


@pytest.mark.django_db
def test_article_list_for_diocese_only_published():
    # Arrange
    diocese = DioceseFactory()
    DioceseArticleFactory(scope_diocese=diocese, status=Article.Status.DRAFT)
    PublishedDioceseArticleFactory(scope_diocese=diocese)

    # Act
    result = article_list_for_diocese(diocese_id=diocese.id)

    # Assert
    assert result.count() == 1
    assert result.first().status == Article.Status.PUBLISHED


# ---------------------------------------------------------------------------
# article_get
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_article_get_returns_article_by_uuid():
    # Arrange
    article = PublishedArticleFactory()

    # Act
    result = article_get(article_id=str(article.id))

    # Assert
    assert result is not None
    assert result.id == article.id


@pytest.mark.django_db
def test_article_get_returns_none_when_not_found():
    # Act
    result = article_get(article_id="00000000-0000-0000-0000-000000000000")

    # Assert
    assert result is None


# ---------------------------------------------------------------------------
# article_get_by_slug
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_article_get_by_slug_returns_article():
    # Arrange
    article = PublishedArticleFactory(slug="mon-article-test")

    # Act
    result = article_get_by_slug(slug="mon-article-test")

    # Assert
    assert result is not None
    assert result.id == article.id


@pytest.mark.django_db
def test_article_get_by_slug_returns_none_when_not_found():
    # Act
    result = article_get_by_slug(slug="inexistant")

    # Assert
    assert result is None

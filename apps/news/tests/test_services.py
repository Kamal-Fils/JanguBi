"""
Tests des services apps/news.
Couvre : article_create, article_update, article_publish, article_unpublish, article_delete.
"""

import pytest

from apps.core.exceptions import ApplicationError
from apps.news.models import Article
from apps.news.services import (
    article_create,
    article_delete,
    article_increment_views,
    article_publish,
    article_unpublish,
    article_update,
)
from apps.users.tests.factories import BaseUserFactory, StaffUserFactory

from .factories import ArticleCategoryFactory, ArticleFactory, PublishedArticleFactory


# ---------------------------------------------------------------------------
# article_create
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_article_create_global_success():
    # Arrange
    author = StaffUserFactory()
    category = ArticleCategoryFactory()

    # Act
    article = article_create(
        author=author,
        title="Actualité de l'Église",
        content="Contenu de l'article.",
        category_id=category.id,
    )

    # Assert
    assert article.id is not None
    assert article.title == "Actualité de l'Église"
    assert article.status == Article.Status.DRAFT
    assert article.scope_type == Article.ScopeType.GLOBAL
    assert article.author == author
    assert article.category == category


@pytest.mark.django_db
def test_article_create_parish_scope_success():
    # Arrange
    author = StaffUserFactory()
    category = ArticleCategoryFactory()

    # Act
    article = article_create(
        author=author,
        title="Messe dominicale",
        content="Contenu.",
        category_id=category.id,
        scope_type=Article.ScopeType.PARISH,
        scope_parish_id=42,
    )

    # Assert
    assert article.scope_type == Article.ScopeType.PARISH
    assert article.scope_parish_id == 42


@pytest.mark.django_db
def test_article_create_diocese_scope_success():
    # Arrange
    author = StaffUserFactory()
    category = ArticleCategoryFactory()

    # Act
    article = article_create(
        author=author,
        title="Nouvelle du diocèse",
        content="Contenu.",
        category_id=category.id,
        scope_type=Article.ScopeType.DIOCESE,
        scope_diocese_id=7,
    )

    # Assert
    assert article.scope_type == Article.ScopeType.DIOCESE
    assert article.scope_diocese_id == 7


@pytest.mark.django_db
def test_article_create_raises_if_fidele():
    # Arrange
    fidele = BaseUserFactory()
    category = ArticleCategoryFactory()

    # Act & Assert
    with pytest.raises(ApplicationError, match="administrateurs"):
        article_create(
            author=fidele,
            title="Test",
            content="Contenu.",
            category_id=category.id,
        )


@pytest.mark.django_db
def test_article_create_raises_if_parish_scope_without_parish_id():
    # Arrange
    author = StaffUserFactory()
    category = ArticleCategoryFactory()

    # Act & Assert
    with pytest.raises(ApplicationError, match="scope_parish_id"):
        article_create(
            author=author,
            title="Test",
            content="Contenu.",
            category_id=category.id,
            scope_type=Article.ScopeType.PARISH,
        )


@pytest.mark.django_db
def test_article_create_raises_if_global_with_parish_id():
    # Arrange
    author = StaffUserFactory()
    category = ArticleCategoryFactory()

    # Act & Assert
    with pytest.raises(ApplicationError, match="global"):
        article_create(
            author=author,
            title="Test",
            content="Contenu.",
            category_id=category.id,
            scope_type=Article.ScopeType.GLOBAL,
            scope_parish_id=1,
        )


@pytest.mark.django_db
def test_article_create_raises_if_category_inactive():
    # Arrange
    author = StaffUserFactory()
    category = ArticleCategoryFactory(is_active=False)

    # Act & Assert
    with pytest.raises(ApplicationError, match="Catégorie"):
        article_create(
            author=author,
            title="Test",
            content="Contenu.",
            category_id=category.id,
        )


# ---------------------------------------------------------------------------
# article_update
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_article_update_title_and_content():
    # Arrange
    editor = StaffUserFactory()
    article = ArticleFactory(author=editor)

    # Act
    updated = article_update(
        article=article,
        editor=editor,
        title="Nouveau titre",
        content="Nouveau contenu.",
    )

    # Assert
    assert updated.title == "Nouveau titre"
    assert updated.content == "Nouveau contenu."


@pytest.mark.django_db
def test_article_update_category():
    # Arrange
    editor = StaffUserFactory()
    article = ArticleFactory(author=editor)
    new_category = ArticleCategoryFactory()

    # Act
    updated = article_update(article=article, editor=editor, category_id=new_category.id)

    # Assert
    assert updated.category_id == new_category.id


@pytest.mark.django_db
def test_article_update_raises_if_unpublished():
    # Arrange
    editor = StaffUserFactory()
    article = ArticleFactory(author=editor, status=Article.Status.UNPUBLISHED)

    # Act & Assert
    with pytest.raises(ApplicationError, match="dépublié"):
        article_update(article=article, editor=editor, title="Nouveau titre")


@pytest.mark.django_db
def test_article_update_raises_if_fidele():
    # Arrange
    fidele = BaseUserFactory()
    article = ArticleFactory()

    # Act & Assert
    with pytest.raises(ApplicationError, match="administrateurs"):
        article_update(article=article, editor=fidele, title="Test")


# ---------------------------------------------------------------------------
# article_publish
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_article_publish_sets_status_and_published_at():
    # Arrange
    editor = StaffUserFactory()
    article = ArticleFactory(author=editor)

    # Act
    published = article_publish(article=article, editor=editor)

    # Assert
    assert published.status == Article.Status.PUBLISHED
    assert published.published_at is not None


@pytest.mark.django_db
def test_article_publish_raises_if_already_published():
    # Arrange
    editor = StaffUserFactory()
    article = PublishedArticleFactory(author=editor)

    # Act & Assert
    with pytest.raises(ApplicationError, match="déjà publié"):
        article_publish(article=article, editor=editor)


@pytest.mark.django_db
def test_article_publish_raises_if_fidele():
    # Arrange
    fidele = BaseUserFactory()
    article = ArticleFactory()

    # Act & Assert
    with pytest.raises(ApplicationError, match="administrateurs"):
        article_publish(article=article, editor=fidele)


# ---------------------------------------------------------------------------
# article_unpublish
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_article_unpublish_sets_status_and_reason():
    # Arrange
    editor = StaffUserFactory()
    article = PublishedArticleFactory(author=editor)

    # Act
    unpublished = article_unpublish(
        article=article, editor=editor, reason="Contenu obsolète."
    )

    # Assert
    assert unpublished.status == Article.Status.UNPUBLISHED
    assert unpublished.unpublished_at is not None
    assert unpublished.unpublished_by == editor
    assert unpublished.unpublish_reason == "Contenu obsolète."


@pytest.mark.django_db
def test_article_unpublish_without_reason_succeeds():
    # Arrange
    editor = StaffUserFactory()
    article = PublishedArticleFactory(author=editor)

    # Act
    unpublished = article_unpublish(article=article, editor=editor)

    # Assert
    assert unpublished.status == Article.Status.UNPUBLISHED
    assert unpublished.unpublish_reason == ""


@pytest.mark.django_db
def test_article_unpublish_raises_if_not_published():
    # Arrange
    editor = StaffUserFactory()
    article = ArticleFactory(author=editor, status=Article.Status.DRAFT)

    # Act & Assert
    with pytest.raises(ApplicationError, match="publié"):
        article_unpublish(article=article, editor=editor)


# ---------------------------------------------------------------------------
# article_delete
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_article_delete_draft_success():
    # Arrange
    editor = StaffUserFactory()
    article = ArticleFactory(author=editor)
    article_id = article.id

    # Act
    article_delete(article=article, editor=editor)

    # Assert
    assert not Article.objects.filter(pk=article_id).exists()


@pytest.mark.django_db
def test_article_delete_unpublished_success():
    # Arrange
    editor = StaffUserFactory()
    article = ArticleFactory(author=editor, status=Article.Status.UNPUBLISHED)
    article_id = article.id

    # Act
    article_delete(article=article, editor=editor)

    # Assert
    assert not Article.objects.filter(pk=article_id).exists()


@pytest.mark.django_db
def test_article_delete_published_raises():
    # Arrange
    editor = StaffUserFactory()
    article = PublishedArticleFactory(author=editor)

    # Act & Assert
    with pytest.raises(ApplicationError, match="publié"):
        article_delete(article=article, editor=editor)


@pytest.mark.django_db
def test_article_delete_raises_if_fidele():
    # Arrange
    fidele = BaseUserFactory()
    article = ArticleFactory()

    # Act & Assert
    with pytest.raises(ApplicationError, match="administrateurs"):
        article_delete(article=article, editor=fidele)


# ---------------------------------------------------------------------------
# article_increment_views
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_article_increment_views_increases_count():
    # Arrange
    article = PublishedArticleFactory(views_count=0)

    # Act
    article_increment_views(article=article)

    # Assert
    article.refresh_from_db()
    assert article.views_count == 1


@pytest.mark.django_db
def test_article_increment_views_is_cumulative():
    # Arrange
    article = PublishedArticleFactory(views_count=5)

    # Act
    article_increment_views(article=article)
    article_increment_views(article=article)

    # Assert
    article.refresh_from_db()
    assert article.views_count == 7


@pytest.mark.django_db
def test_article_increment_views_uses_database_update():
    # Arrange — verify the F() expression works correctly
    article = PublishedArticleFactory(views_count=100)

    # Act
    article_increment_views(article=article)

    # Assert — database value is authoritative
    from apps.news.models import Article as ArticleModel

    db_value = ArticleModel.objects.values_list("views_count", flat=True).get(pk=article.pk)
    assert db_value == 101

"""
Tests des services TV — HackSoft Styleguide.
Pattern AAA (Arrange / Act / Assert) sur chaque test.
"""

import pytest

from apps.core.exceptions import ApplicationError
from apps.tv.models import Category, Video
from apps.tv.services import (
    category_create,
    category_delete,
    category_update,
    video_create,
    video_delete,
    video_update,
)
from apps.tv.tests.factories import CategoryFactory, VideoFactory

# ---------------------------------------------------------------------------
# category_create
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_category_create_success():
    # Act
    category = category_create(name="Messes")

    # Assert
    assert category.id is not None
    assert category.name == "Messes"
    assert category.order == 0
    assert Category.objects.filter(id=category.id).exists()


@pytest.mark.django_db
def test_category_create_with_explicit_order():
    # Act
    category = category_create(name="Enseignement", order=5)

    # Assert
    assert category.order == 5


@pytest.mark.django_db
def test_category_create_generates_slug_from_name():
    # Act
    category = category_create(name="Messes du Dimanche")

    # Assert
    assert category.slug is not None
    assert len(category.slug) > 0


# ---------------------------------------------------------------------------
# category_update
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_category_update_modifies_name():
    # Arrange
    category = CategoryFactory(name="Ancien nom")

    # Act
    updated = category_update(category=category, name="Nouveau nom")

    # Assert
    assert updated.name == "Nouveau nom"
    category.refresh_from_db()
    assert category.name == "Nouveau nom"


@pytest.mark.django_db
def test_category_update_modifies_order():
    # Arrange
    category = CategoryFactory(order=1)

    # Act
    updated = category_update(category=category, order=10)

    # Assert
    assert updated.order == 10


@pytest.mark.django_db
def test_category_update_returns_category_instance():
    # Arrange
    category = CategoryFactory()

    # Act
    result = category_update(category=category, name="Updated")

    # Assert
    assert isinstance(result, Category)


# ---------------------------------------------------------------------------
# category_delete
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_category_delete_removes_category():
    # Arrange
    category = CategoryFactory()
    category_id = category.id

    # Act
    category_delete(category=category)

    # Assert
    assert not Category.objects.filter(id=category_id).exists()


# ---------------------------------------------------------------------------
# video_delete
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_video_delete_removes_video():
    # Arrange
    video = VideoFactory()
    video_id = video.id

    # Act
    video_delete(video=video)

    # Assert
    assert not Video.objects.filter(id=video_id).exists()


# ---------------------------------------------------------------------------
# video_create
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_video_create_success():
    # Arrange
    category = CategoryFactory(slug="messes")

    # Act
    video = video_create(
        title="Homélie du dimanche",
        youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        category_slug="messes",
        is_live=False,
        is_pinned_live=False,
    )

    # Assert
    assert video.id is not None
    assert video.category == category
    assert video.title == "Homélie du dimanche"
    assert Video.objects.filter(id=video.id).exists()


@pytest.mark.django_db
def test_video_create_raises_when_category_not_found():
    # Act & Assert
    with pytest.raises(ApplicationError, match="introuvable"):
        video_create(
            title="Test",
            youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            category_slug="nonexistent-slug",
        )


@pytest.mark.django_db
def test_video_create_extracts_youtube_id():
    # Arrange
    CategoryFactory(slug="messes")

    # Act
    video = video_create(
        title="Test video",
        youtube_url="https://youtu.be/5NV6Rdv1a3I",
        category_slug="messes",
    )

    # Assert
    assert video.youtube_id == "5NV6Rdv1a3I"


# ---------------------------------------------------------------------------
# video_update
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_video_update_success():
    # Arrange
    video = VideoFactory(title="Ancien titre")

    # Act
    updated = video_update(video=video, title="Nouveau titre")

    # Assert
    assert updated.title == "Nouveau titre"
    video.refresh_from_db()
    assert video.title == "Nouveau titre"


@pytest.mark.django_db
def test_video_update_changes_category():
    # Arrange
    old_category = CategoryFactory(slug="messes")
    new_category = CategoryFactory(slug="enseignement")
    video = VideoFactory(category=old_category)

    # Act
    updated = video_update(video=video, category_slug="enseignement")

    # Assert
    assert updated.category == new_category


@pytest.mark.django_db
def test_video_update_raises_when_new_category_not_found():
    # Arrange
    video = VideoFactory()

    # Act & Assert
    with pytest.raises(ApplicationError, match="introuvable"):
        video_update(video=video, category_slug="nonexistent")

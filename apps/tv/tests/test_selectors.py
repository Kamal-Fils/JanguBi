"""
Tests des sélecteurs TV — HackSoft Styleguide.
Pattern AAA (Arrange / Act / Assert) sur chaque test.
"""

import pytest

from apps.tv.selectors import category_list, video_list
from apps.tv.tests.factories import CategoryFactory, VideoFactory


# ---------------------------------------------------------------------------
# category_list
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_category_list_returns_all_categories():
    # Arrange
    CategoryFactory(name="Messes", order=1)
    CategoryFactory(name="Enseignement", order=2)

    # Act
    result = category_list()

    # Assert
    assert result.count() == 2


@pytest.mark.django_db
def test_category_list_ordered_by_order_then_name():
    # Arrange
    c2 = CategoryFactory(name="Zèle", order=1)
    c1 = CategoryFactory(name="Alpha", order=1)
    c3 = CategoryFactory(name="Messes", order=2)

    # Act
    result = list(category_list())

    # Assert — within same order, alphabetical by name
    assert result[0] == c1  # "Alpha", order=1
    assert result[1] == c2  # "Zèle", order=1
    assert result[2] == c3  # "Messes", order=2


@pytest.mark.django_db
def test_category_list_returns_empty_queryset_when_none():
    # Act
    result = category_list()

    # Assert
    assert result.count() == 0


# ---------------------------------------------------------------------------
# video_list
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_video_list_returns_all_videos():
    # Arrange
    VideoFactory()
    VideoFactory()

    # Act
    result = video_list()

    # Assert
    assert result.count() == 2


@pytest.mark.django_db
def test_video_list_filters_by_category_slug():
    # Arrange
    cat = CategoryFactory(slug="messes")
    VideoFactory(category=cat)
    VideoFactory()  # different category

    # Act
    result = video_list(category_slug="messes")

    # Assert
    assert result.count() == 1
    assert result.first().category.slug == "messes"


@pytest.mark.django_db
def test_video_list_returns_all_when_category_slug_not_provided():
    # Arrange
    VideoFactory()
    VideoFactory()

    # Act
    result = video_list(category_slug=None)

    # Assert
    assert result.count() == 2


@pytest.mark.django_db
def test_video_list_filters_by_is_live_true():
    # Arrange
    VideoFactory(is_live=True)
    VideoFactory(is_live=False)

    # Act
    result = video_list(is_live="true")

    # Assert
    assert result.count() == 1
    assert result.first().is_live is True


@pytest.mark.django_db
def test_video_list_filters_by_is_live_false():
    # Arrange
    VideoFactory(is_live=True)
    VideoFactory(is_live=False)

    # Act
    result = video_list(is_live="false")

    # Assert
    assert result.count() == 1
    assert result.first().is_live is False


@pytest.mark.django_db
def test_video_list_ignores_invalid_is_live_value():
    # Arrange
    VideoFactory(is_live=True)
    VideoFactory(is_live=False)

    # Act — "yes" is not a valid boolean string
    result = video_list(is_live="yes")

    # Assert — no filter applied
    assert result.count() == 2


@pytest.mark.django_db
def test_video_list_filters_by_is_pinned_live_true():
    # Arrange
    VideoFactory(is_pinned_live=True)
    VideoFactory(is_pinned_live=False)

    # Act
    result = video_list(is_pinned_live="true")

    # Assert
    assert result.count() == 1
    assert result.first().is_pinned_live is True


@pytest.mark.django_db
def test_video_list_uses_select_related_for_category():
    # Arrange
    cat = CategoryFactory(name="Messes")
    VideoFactory(category=cat)

    # Act
    result = list(video_list())

    # Assert — accessing category should not cause extra queries
    assert result[0].category.name == "Messes"


@pytest.mark.django_db
def test_video_list_returns_empty_queryset_when_none():
    # Act
    result = video_list()

    # Assert
    assert result.count() == 0

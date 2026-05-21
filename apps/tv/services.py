from django.conf import settings
from django.db import transaction
from django.utils.text import slugify

from apps.core.exceptions import ApplicationError
from apps.tv.models import Category, Video
from apps.tv.utils.youtube import extract_youtube_video_id, fetch_youtube_metadata

_DEFAULT_CATEGORIES = [
    ("Messes", "messes", 1),
    ("Enseignement", "enseignement", 2),
    ("Documentaires", "documentaires", 3),
    ("Reportages", "reportages", 4),
]


@transaction.atomic
def category_create(*, name: str, order: int = 0) -> Category:
    category = Category(name=name, slug=slugify(name), order=order)
    category.full_clean()
    category.save()
    return category


@transaction.atomic
def category_update(*, category: Category, name: str | None = None, order: int | None = None) -> Category:
    if name is not None:
        category.name = name
    if order is not None:
        category.order = order
    category.full_clean()
    category.save()
    return category


@transaction.atomic
def category_delete(*, category: Category) -> None:
    category.delete()


@transaction.atomic
def video_delete(*, video: Video) -> None:
    video.delete()


@transaction.atomic
def category_ensure_defaults() -> int:
    created_count = 0
    for name, slug, order in _DEFAULT_CATEGORIES:
        _, created = Category.objects.get_or_create(
            slug=slug,
            defaults={"name": name, "order": order},
        )
        if created:
            created_count += 1
    return created_count


def _enrich_if_possible(
    *,
    youtube_url: str,
    title: str,
    is_live: bool | None,
) -> tuple[str, bool | None]:
    """Fetch YouTube metadata and fill in missing values.
    Returns (title, is_live). is_live stays None if not explicitly provided and YouTube is unavailable.
    """
    video_id = extract_youtube_video_id(youtube_url)
    if not video_id:
        return title, is_live

    api_key = getattr(settings, "YOUTUBE_API_KEY", "")
    if not api_key:
        return title, is_live

    metadata = fetch_youtube_metadata(video_id=video_id, api_key=api_key)
    if not metadata:
        return title, is_live

    enriched_title = title.strip() or metadata.get("title", "")
    enriched_is_live = is_live if is_live is not None else bool(metadata.get("is_live", False))
    return enriched_title, enriched_is_live


@transaction.atomic
def video_create(
    *,
    category_slug: str,
    youtube_url: str,
    title: str = "",
    is_live: bool | None = None,
    is_pinned_live: bool = False,
) -> Video:
    from apps.tv.selectors import category_get_by_slug

    category = category_get_by_slug(slug=category_slug)
    if not category:
        raise ApplicationError(f"Catégorie '{category_slug}' introuvable.")

    enriched_title, enriched_is_live = _enrich_if_possible(
        youtube_url=youtube_url,
        title=title,
        is_live=is_live,
    )
    video = Video(
        category=category,
        youtube_url=youtube_url,
        title=enriched_title,
        is_live=enriched_is_live if enriched_is_live is not None else False,
        is_pinned_live=is_pinned_live,
    )
    video.full_clean()
    video.save()
    return video


@transaction.atomic
def video_update(
    *,
    video: Video,
    category_slug: str | None = None,
    youtube_url: str | None = None,
    title: str | None = None,
    is_live: bool | None = None,
    is_pinned_live: bool | None = None,
) -> Video:
    from apps.tv.selectors import category_get_by_slug

    if category_slug is not None:
        category = category_get_by_slug(slug=category_slug)
        if not category:
            raise ApplicationError(f"Catégorie '{category_slug}' introuvable.")
        video.category = category

    effective_url = youtube_url if youtube_url is not None else video.youtube_url
    enriched_title, enriched_is_live = _enrich_if_possible(
        youtube_url=effective_url,
        title=title or "",
        is_live=is_live,
    )

    if youtube_url is not None:
        video.youtube_url = youtube_url
    if title is not None or enriched_title:
        video.title = enriched_title
    if enriched_is_live is not None:
        video.is_live = enriched_is_live
    if is_pinned_live is not None:
        video.is_pinned_live = is_pinned_live

    video.full_clean()
    video.save()
    return video

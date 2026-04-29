from django.conf import settings
from django.db import transaction

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


class TvService:
    @staticmethod
    def _get_category_or_error(slug: str) -> Category:
        category = Category.objects.filter(slug=slug).first()
        if not category:
            raise ApplicationError(f"Catégorie '{slug}' introuvable.")
        return category

    @staticmethod
    def _enrich_if_possible(video_data: dict, youtube_url: str) -> dict:
        video_id = extract_youtube_video_id(youtube_url)
        if not video_id:
            return video_data

        api_key = getattr(settings, "YOUTUBE_API_KEY", "")
        if not api_key:
            return video_data

        metadata = fetch_youtube_metadata(video_id=video_id, api_key=api_key)
        if not metadata:
            return video_data

        title = (video_data.get("title") or "").strip()
        if not title:
            video_data["title"] = metadata.get("title", "")

        if "is_live" not in video_data:
            video_data["is_live"] = bool(metadata.get("is_live", False))

        return video_data

    @classmethod
    @transaction.atomic
    def create_video(cls, validated_data: dict) -> Video:
        category_slug = validated_data.pop("category_slug")
        category = cls._get_category_or_error(category_slug)

        payload = cls._enrich_if_possible(validated_data, validated_data.get("youtube_url", ""))
        video = Video(category=category, **payload)
        video.full_clean()
        video.save()
        return video

    @classmethod
    @transaction.atomic
    def update_video(cls, video: Video, validated_data: dict) -> Video:
        category_slug = validated_data.pop("category_slug", None)
        if category_slug is not None:
            video.category = cls._get_category_or_error(category_slug)

        new_url = validated_data.get("youtube_url", video.youtube_url)
        payload = cls._enrich_if_possible(validated_data, new_url)

        for field, value in payload.items():
            setattr(video, field, value)

        video.full_clean()
        video.save()
        return video

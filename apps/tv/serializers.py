from rest_framework import serializers

from apps.tv.models import Category, Video
from apps.tv.utils.youtube import extract_youtube_video_id


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug", "order", "is_clergy_only", "created_at", "updated_at"]
        read_only_fields = ["slug", "created_at", "updated_at"]


class VideoListSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    youtube_id = serializers.CharField(read_only=True)
    embed_url = serializers.CharField(read_only=True)

    class Meta:
        model = Video
        fields = [
            "id",
            "title",
            "youtube_url",
            "youtube_id",
            "embed_url",
            "category",
            "is_live",
            "is_pinned_live",
            "created_at",
            "updated_at",
        ]


class VideoCreateUpdateSerializer(serializers.ModelSerializer):
    category_slug = serializers.CharField(write_only=True)

    class Meta:
        model = Video
        fields = ["title", "youtube_url", "category_slug", "is_live", "is_pinned_live"]
        extra_kwargs = {
            "title": {"required": False, "allow_blank": True},
            "is_live": {"required": False},
            "is_pinned_live": {"required": False},
        }

    def validate_youtube_url(self, value):
        if not extract_youtube_video_id(value):
            raise serializers.ValidationError("Invalid YouTube URL. Unable to extract a valid video ID.")
        return value

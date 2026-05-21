from rest_framework import serializers

from apps.news.models import Article, ArticleCategory


def _author_display(user) -> str:
    profile = getattr(user, "profile", None)
    if profile:
        name = f"{profile.first_name} {profile.last_name}".strip()
        if name:
            return name
    return user.email


# ---------------------------------------------------------------------------
# Input serializers
# ---------------------------------------------------------------------------


class ArticleCreateInputSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    content = serializers.CharField()
    category_id = serializers.IntegerField()
    content_type = serializers.ChoiceField(
        choices=Article.ContentType.choices,
        default=Article.ContentType.ARTICLE,
        required=False,
    )
    excerpt = serializers.CharField(max_length=400, required=False, allow_blank=True, default="")
    cover_image_id = serializers.IntegerField(required=False, allow_null=True)
    scope_type = serializers.ChoiceField(
        choices=Article.ScopeType.choices,
        default=Article.ScopeType.GLOBAL,
    )
    scope_parish_id = serializers.IntegerField(required=False, allow_null=True)
    scope_diocese_id = serializers.IntegerField(required=False, allow_null=True)


class ArticleUpdateInputSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, required=False)
    excerpt = serializers.CharField(max_length=400, required=False, allow_blank=True)
    content = serializers.CharField(required=False)
    category_id = serializers.IntegerField(required=False)
    cover_image_id = serializers.IntegerField(required=False, allow_null=True)


class ArticleUnpublishInputSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")


# ---------------------------------------------------------------------------
# Output serializers
# ---------------------------------------------------------------------------


class ArticleCategoryOutputSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArticleCategory
        fields = ["id", "name", "slug", "icon", "color", "display_order"]


class ArticleListOutputSerializer(serializers.ModelSerializer):
    category = ArticleCategoryOutputSerializer(read_only=True)
    author_name = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()
    scope_type_label = serializers.CharField(source="get_scope_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    content_type_label = serializers.CharField(source="get_content_type_display", read_only=True)

    class Meta:
        model = Article
        fields = [
            "id",
            "title",
            "slug",
            "excerpt",
            "cover_image_url",
            "category",
            "author_name",
            "content_type",
            "content_type_label",
            "scope_type",
            "scope_type_label",
            "scope_parish_id",
            "scope_diocese_id",
            "status",
            "status_label",
            "views_count",
            "published_at",
            "created_at",
        ]

    def get_author_name(self, obj) -> str:
        return _author_display(obj.author)

    def get_cover_image_url(self, obj) -> str | None:
        if not obj.cover_image_id or not obj.cover_image.file:
            return None
        return obj.cover_image.url


class ArticleDetailOutputSerializer(serializers.ModelSerializer):
    category = ArticleCategoryOutputSerializer(read_only=True)
    author_name = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()
    scope_type_label = serializers.CharField(source="get_scope_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    content_type_label = serializers.CharField(source="get_content_type_display", read_only=True)
    unpublished_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Article
        fields = [
            "id",
            "title",
            "slug",
            "excerpt",
            "content",
            "cover_image_url",
            "category",
            "author_name",
            "content_type",
            "content_type_label",
            "scope_type",
            "scope_type_label",
            "scope_parish_id",
            "scope_diocese_id",
            "status",
            "status_label",
            "views_count",
            "published_at",
            "unpublished_at",
            "unpublished_by_name",
            "unpublish_reason",
            "created_at",
            "updated_at",
        ]

    def get_author_name(self, obj) -> str:
        return _author_display(obj.author)

    def get_cover_image_url(self, obj) -> str | None:
        if not obj.cover_image_id or not obj.cover_image.file:
            return None
        return obj.cover_image.url

    def get_unpublished_by_name(self, obj) -> str | None:
        if obj.unpublished_by is None:
            return None
        return _author_display(obj.unpublished_by)

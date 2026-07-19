from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.news.models import Article, ArticleCategory, ArticleReaction

_REACTION_TYPES: tuple[str, ...] = tuple(ArticleReaction.ReactionType.values)


class ArticleReactionsOutputSerializer(serializers.Serializer):
    """Bloc `reactions` embarqué dans la liste ET le détail d'article.

    Le front a besoin des deux d'un coup — combien, et est-ce que MOI j'ai
    réagi — sinon il repart chercher l'état article par article et le fil paie
    une requête réseau par carte.
    """

    counts = serializers.DictField(
        child=serializers.IntegerField(),
        help_text="Nombre de réactions par type : pray / amen / attend.",
    )
    mine = serializers.ListField(
        child=serializers.ChoiceField(choices=ArticleReaction.ReactionType.choices),
        help_text="Types déjà posés par l'utilisateur courant (vide si anonyme).",
    )


def _reactions_payload(obj) -> dict:
    """Lit les ANNOTATIONS posées par `annotate_reactions` — jamais la relation.

    Le repli à 0 / [] est volontairement muet : un accès à `obj.reactions` ici
    déclencherait une requête par article et réintroduirait exactement le N+1
    que l'annotation existe pour éviter.
    """
    return {
        "counts": {
            reaction_type: getattr(obj, f"reaction_{reaction_type}_count", 0) or 0
            for reaction_type in _REACTION_TYPES
        },
        "mine": [
            reaction_type
            for reaction_type in _REACTION_TYPES
            if getattr(obj, f"reaction_{reaction_type}_mine", False)
        ],
    }


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
    content_format = serializers.ChoiceField(
        choices=Article.ContentFormat.choices,
        default=Article.ContentFormat.TEXT,
        required=False,
        help_text="'html' pour l'éditeur riche (sanitizé côté serveur), 'text' sinon.",
    )
    announcement_date = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Annonces : date du jour concerné (ex. dimanche à venir).",
    )
    excerpt = serializers.CharField(max_length=400, required=False, allow_blank=True, default="")
    cover_image_id = serializers.IntegerField(required=False, allow_null=True)
    scope_type = serializers.ChoiceField(
        choices=Article.ScopeType.choices,
        default=Article.ScopeType.GLOBAL,
    )
    scope_parish_id = serializers.IntegerField(required=False, allow_null=True)
    scope_diocese_id = serializers.IntegerField(required=False, allow_null=True)
    scope_church_id = serializers.IntegerField(required=False, allow_null=True)


class ArticleUpdateInputSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, required=False)
    excerpt = serializers.CharField(max_length=400, required=False, allow_blank=True)
    content = serializers.CharField(required=False)
    content_format = serializers.ChoiceField(
        choices=Article.ContentFormat.choices, required=False
    )
    announcement_date = serializers.DateField(required=False, allow_null=True)
    category_id = serializers.IntegerField(required=False)
    cover_image_id = serializers.IntegerField(required=False, allow_null=True)


class ArticleUnpublishInputSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class ArticleReactionSetInputSerializer(serializers.Serializer):
    """État VOULU d'une réaction — pas une bascule.

    `active` est explicite pour que rejouer la requête soit sans effet : une
    bascule implicite ferait repartir un double-clic dans l'autre sens.
    """

    reaction_type = serializers.ChoiceField(
        choices=ArticleReaction.ReactionType.choices,
        help_text="pray (Je prie) · amen (Amen) · attend (Je participe).",
    )
    active = serializers.BooleanField(
        help_text="true pour poser la réaction, false pour la retirer.",
    )


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
    # FK exposées en ids (contrat front inchangé) ; +scope_church_id (Chantier 3a).
    scope_parish_id = serializers.IntegerField(read_only=True, allow_null=True)
    scope_diocese_id = serializers.IntegerField(read_only=True, allow_null=True)
    scope_church_id = serializers.IntegerField(read_only=True, allow_null=True)
    reactions = serializers.SerializerMethodField()

    class Meta:
        model = Article
        fields = [
            "id",
            "title",
            "slug",
            "excerpt",
            "cover_image_url",
            "reactions",
            "category",
            "author_name",
            "content_type",
            "content_type_label",
            "announcement_date",
            "scope_type",
            "scope_type_label",
            "scope_parish_id",
            "scope_diocese_id",
            "scope_church_id",
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

    @extend_schema_field(ArticleReactionsOutputSerializer)
    def get_reactions(self, obj) -> dict:
        return _reactions_payload(obj)


class ArticleDetailOutputSerializer(serializers.ModelSerializer):
    category = ArticleCategoryOutputSerializer(read_only=True)
    author_name = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()
    scope_type_label = serializers.CharField(source="get_scope_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    content_type_label = serializers.CharField(source="get_content_type_display", read_only=True)
    unpublished_by_name = serializers.SerializerMethodField()
    # FK exposées en ids (contrat front inchangé) ; +scope_church_id (Chantier 3a).
    scope_parish_id = serializers.IntegerField(read_only=True, allow_null=True)
    scope_diocese_id = serializers.IntegerField(read_only=True, allow_null=True)
    scope_church_id = serializers.IntegerField(read_only=True, allow_null=True)
    reactions = serializers.SerializerMethodField()

    class Meta:
        model = Article
        fields = [
            "id",
            "title",
            "slug",
            "excerpt",
            "content",
            "content_format",
            "cover_image_url",
            "reactions",
            "category",
            "author_name",
            "content_type",
            "content_type_label",
            "announcement_date",
            "scope_type",
            "scope_type_label",
            "scope_parish_id",
            "scope_diocese_id",
            "scope_church_id",
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

    @extend_schema_field(ArticleReactionsOutputSerializer)
    def get_reactions(self, obj) -> dict:
        return _reactions_payload(obj)

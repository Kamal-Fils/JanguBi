from django.contrib import admin

from apps.news.models import Article, ArticleCategory


@admin.register(ArticleCategory)
class ArticleCategoryAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "slug", "display_order", "is_active"]
    list_editable = ["display_order", "is_active"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}
    ordering = ["display_order", "name"]


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "category", "scope_type", "status", "author", "published_at", "created_at"]
    list_filter = ["status", "scope_type", "category"]
    search_fields = ["title", "slug", "content"]
    raw_id_fields = ["author", "cover_image", "unpublished_by"]
    readonly_fields = [
        "id", "slug", "views_count", "published_at", "unpublished_at", "created_at", "updated_at"
    ]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]

    fieldsets = (
        ("Contenu", {"fields": ("title", "slug", "excerpt", "content", "cover_image", "category")}),
        ("Portée", {"fields": ("scope_type", "scope_parish_id", "scope_diocese_id")}),
        ("Publication", {"fields": ("status", "author", "published_at")}),
        (
            "Dépublication",
            {
                "fields": ("unpublished_at", "unpublished_by", "unpublish_reason"),
                "classes": ("collapse",),
            },
        ),
        (
            "Métadonnées",
            {
                "fields": ("id", "views_count", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

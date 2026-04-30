import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel
from apps.files.models import File
from apps.users.models import BaseUser


class ArticleCategory(models.Model):
    """Catégorie d'article (ex: Annonces, Événements, Vie paroissiale)."""

    name = models.CharField(max_length=100, verbose_name=_("Nom"))
    slug = models.SlugField(max_length=110, unique=True, verbose_name=_("Slug"))
    icon = models.CharField(max_length=50, blank=True, default="", verbose_name=_("Icône"))
    color = models.CharField(max_length=7, blank=True, default="", verbose_name=_("Couleur hex"))
    display_order = models.IntegerField(default=0, db_index=True, verbose_name=_("Ordre d'affichage"))
    is_active = models.BooleanField(default=True, db_index=True, verbose_name=_("Active"))

    class Meta:
        verbose_name = _("Catégorie d'article")
        verbose_name_plural = _("Catégories d'article")
        ordering = ["display_order", "name"]

    def __str__(self) -> str:
        return self.name


class Article(BaseModel):
    """
    Article éditorial publié à un niveau de portée (global, diocèse, paroisse).

    scope_parish_id et scope_diocese_id sont des IntegerField placeholder
    en attendant que le module Organisation (Parish, Diocese) soit implémenté (V2).
    """

    class ScopeType(models.TextChoices):
        GLOBAL = "global", _("Global (toute l'Église du Sénégal)")
        DIOCESE = "diocese", _("Diocèse")
        PARISH = "parish", _("Paroisse")

    class Status(models.TextChoices):
        DRAFT = "draft", _("Brouillon")
        PUBLISHED = "published", _("Publié")
        UNPUBLISHED = "unpublished", _("Dépublié")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    title = models.CharField(max_length=200, verbose_name=_("Titre"))
    slug = models.SlugField(max_length=220, verbose_name=_("Slug"))
    excerpt = models.CharField(
        max_length=400, blank=True, default="", verbose_name=_("Résumé court")
    )
    content = models.TextField(verbose_name=_("Contenu"))

    cover_image = models.ForeignKey(
        File,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="article_covers",
        verbose_name=_("Image de couverture"),
    )

    category = models.ForeignKey(
        ArticleCategory,
        on_delete=models.PROTECT,
        related_name="articles",
        verbose_name=_("Catégorie"),
    )

    author = models.ForeignKey(
        BaseUser,
        on_delete=models.PROTECT,
        related_name="articles",
        verbose_name=_("Auteur"),
    )

    # --- Portée ---
    scope_type = models.CharField(
        max_length=20,
        choices=ScopeType.choices,
        default=ScopeType.GLOBAL,
        db_index=True,
        verbose_name=_("Portée"),
    )
    # Placeholders — seront remplacés par FK réelles quand le module ORG sera livré (V2)
    scope_parish_id = models.IntegerField(
        null=True, blank=True, db_index=True, verbose_name=_("ID paroisse (placeholder)")
    )
    scope_diocese_id = models.IntegerField(
        null=True, blank=True, db_index=True, verbose_name=_("ID diocèse (placeholder)")
    )

    # --- Statut & workflow ---
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
        verbose_name=_("Statut"),
    )
    published_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Publié le"))
    unpublished_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Dépublié le"))
    unpublished_by = models.ForeignKey(
        BaseUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="unpublished_articles",
        verbose_name=_("Dépublié par"),
    )
    unpublish_reason = models.TextField(
        blank=True, default="", verbose_name=_("Motif de dépublication")
    )

    views_count = models.PositiveIntegerField(default=0, verbose_name=_("Nombre de vues"))

    class Meta:
        verbose_name = _("Article")
        verbose_name_plural = _("Articles")
        ordering = ["-published_at", "-created_at"]
        constraints = [
            # Slug unique par portée paroisse
            models.UniqueConstraint(
                fields=["slug", "scope_type", "scope_parish_id"],
                name="unique_article_slug_parish",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "-published_at"], name="article_status_pub_idx"),
            models.Index(
                fields=["scope_type", "scope_parish_id", "status"],
                name="article_parish_idx",
            ),
            models.Index(
                fields=["scope_type", "scope_diocese_id", "status"],
                name="article_diocese_idx",
            ),
            models.Index(fields=["category", "status"], name="article_category_idx"),
            models.Index(fields=["author", "-created_at"], name="article_author_idx"),
        ]

    def __str__(self) -> str:
        return f"[{self.get_scope_type_display()}] {self.title} ({self.get_status_display()})"

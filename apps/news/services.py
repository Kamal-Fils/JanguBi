from django.db import models
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.core.exceptions import ApplicationError
from apps.news.models import Article, ArticleCategory
from apps.users.enums import PastoralRole, UserRole
from apps.users.models import BaseUser

# Rôles d'administration digitale (UserRole) autorisés à gérer/publier des articles.
_EDITOR_ROLES = {
    UserRole.SUPER_ADMIN,
    UserRole.PROVINCE_ADMIN,
    UserRole.DIOCESE_ADMIN,
    UserRole.PARISH_ADMIN,
    UserRole.CHURCH_ADMIN,
}

# Rôles admin équivalant à un évêque pour publier une lettre pastorale.
_BISHOP_ADMIN_ROLES = {
    UserRole.SUPER_ADMIN,
    UserRole.PROVINCE_ADMIN,
    UserRole.DIOCESE_ADMIN,
}

# Rôles pastoraux (PastoralRole) — dimension orthogonale à `role`.
# eveque/archeveque vivent UNIQUEMENT dans pastoral_role (jamais dans role).
_BISHOP_PASTORAL_ROLES = {PastoralRole.EVEQUE, PastoralRole.ARCHEVEQUE}

# Clergé pouvant créer / gérer un article (brouillon inclus) — diacre compris.
_CLERGY_EDITOR_ROLES = {
    PastoralRole.DIACRE,
    PastoralRole.PRETRE,
    PastoralRole.EVEQUE,
    PastoralRole.ARCHEVEQUE,
}

# Clergé pouvant PUBLIER — diacre EXCLU (brouillon seulement, matrice §16).
_CLERGY_PUBLISHER_ROLES = {
    PastoralRole.PRETRE,
    PastoralRole.EVEQUE,
    PastoralRole.ARCHEVEQUE,
}


# ---------------------------------------------------------------------------
# Helpers d'autorisation — source unique, réutilisée par permissions.py
# ---------------------------------------------------------------------------


def is_bishop(user: BaseUser) -> bool:
    """Évêque/archevêque (pastoral_role) OU admin diocèse-et-plus (role)."""
    return (
        user.pastoral_role in _BISHOP_PASTORAL_ROLES
        or user.role in _BISHOP_ADMIN_ROLES
    )


def is_news_editor(user: BaseUser) -> bool:
    """Peut créer/gérer un article : admin digital OU clergé (diacre inclus)."""
    return (
        user.role in _EDITOR_ROLES
        or user.pastoral_role in _CLERGY_EDITOR_ROLES
    )


def _check_editor(user: BaseUser) -> None:
    if not is_news_editor(user):
        raise ApplicationError("Seuls les administrateurs et le clergé peuvent gérer les articles.")


def article_can_publish(*, user: BaseUser, article: Article) -> bool:
    if article.content_type == Article.ContentType.PASTORAL_LETTER:
        return is_bishop(user)
    # ANNOUNCEMENT et ARTICLE : admin digital OU clergé publicateur (diacre exclu).
    return user.role in _EDITOR_ROLES or user.pastoral_role in _CLERGY_PUBLISHER_ROLES


def _check_scope_consistency(
    scope_type: str,
    scope_parish_id: int | None,
    scope_diocese_id: int | None,
) -> None:
    if scope_type == Article.ScopeType.PARISH and not scope_parish_id:
        raise ApplicationError("Un article de portée 'paroisse' doit avoir un scope_parish_id.")
    if scope_type == Article.ScopeType.DIOCESE and not scope_diocese_id:
        raise ApplicationError("Un article de portée 'diocèse' doit avoir un scope_diocese_id.")
    if scope_type == Article.ScopeType.GLOBAL and (scope_parish_id or scope_diocese_id):
        raise ApplicationError(
            "Un article global ne doit pas avoir de scope_parish_id ou scope_diocese_id."
        )


def _build_slug(title: str, scope_type: str, scope_id: int | None) -> str:
    base = slugify(title)
    suffix = f"{scope_type}-{scope_id}" if scope_id else scope_type
    candidate = f"{base}-{suffix}"
    if not Article.objects.filter(slug=candidate).exists():
        return candidate
    count = Article.objects.filter(slug__startswith=candidate).count()
    return f"{candidate}-{count + 1}"


# ---------------------------------------------------------------------------
# Services publics
# ---------------------------------------------------------------------------


@transaction.atomic
def article_create(
    *,
    author: BaseUser,
    title: str,
    content: str,
    category_id: int,
    scope_type: str = Article.ScopeType.GLOBAL,
    content_type: str = Article.ContentType.ARTICLE,
    excerpt: str = "",
    cover_image_id: int | None = None,
    scope_parish_id: int | None = None,
    scope_diocese_id: int | None = None,
) -> Article:
    _check_editor(author)
    _check_scope_consistency(scope_type, scope_parish_id, scope_diocese_id)

    try:
        category = ArticleCategory.objects.get(pk=category_id, is_active=True)
    except ArticleCategory.DoesNotExist:
        raise ApplicationError(f"Catégorie {category_id} introuvable ou inactive.")

    cover_image = None
    if cover_image_id is not None:
        from apps.files.models import File

        try:
            cover_image = File.objects.get(pk=cover_image_id)
        except File.DoesNotExist:
            raise ApplicationError(f"Fichier {cover_image_id} introuvable.")
        if not cover_image.is_valid:
            raise ApplicationError("Le fichier image n'a pas encore été finalisé.")

    scope_id = scope_parish_id if scope_type == Article.ScopeType.PARISH else scope_diocese_id
    slug = _build_slug(title, scope_type, scope_id)

    return Article.objects.create(
        title=title,
        slug=slug,
        excerpt=excerpt,
        content=content,
        content_type=content_type,
        category=category,
        author=author,
        cover_image=cover_image,
        scope_type=scope_type,
        scope_parish_id=scope_parish_id,
        scope_diocese_id=scope_diocese_id,
        status=Article.Status.DRAFT,
    )


@transaction.atomic
def article_update(
    *,
    article: Article,
    editor: BaseUser,
    title: str | None = None,
    excerpt: str | None = None,
    content: str | None = None,
    category_id: int | None = None,
    cover_image_id: int | None = None,
) -> Article:
    _check_editor(editor)

    if article.status == Article.Status.UNPUBLISHED:
        raise ApplicationError("Un article dépublié ne peut pas être modifié.")

    update_fields = ["updated_at"]

    if title is not None:
        article.title = title
        update_fields.append("title")
    if excerpt is not None:
        article.excerpt = excerpt
        update_fields.append("excerpt")
    if content is not None:
        article.content = content
        update_fields.append("content")

    if category_id is not None:
        try:
            article.category = ArticleCategory.objects.get(pk=category_id, is_active=True)
        except ArticleCategory.DoesNotExist:
            raise ApplicationError(f"Catégorie {category_id} introuvable ou inactive.")
        update_fields.append("category")

    if cover_image_id is not None:
        from apps.files.models import File

        try:
            img = File.objects.get(pk=cover_image_id)
        except File.DoesNotExist:
            raise ApplicationError(f"Fichier {cover_image_id} introuvable.")
        if not img.is_valid:
            raise ApplicationError("Le fichier image n'a pas encore été finalisé.")
        article.cover_image = img
        update_fields.append("cover_image")

    article.save(update_fields=update_fields)
    return article


@transaction.atomic
def article_publish(*, article: Article, editor: BaseUser) -> Article:
    _check_editor(editor)
    if not article_can_publish(user=editor, article=article):
        raise ApplicationError(
            "Vous n'avez pas les droits nécessaires pour publier ce type de contenu."
        )

    if article.status == Article.Status.PUBLISHED:
        raise ApplicationError("L'article est déjà publié.")

    article.status = Article.Status.PUBLISHED
    article.published_at = timezone.now()
    article.save(update_fields=["status", "published_at", "updated_at"])
    return article


@transaction.atomic
def article_unpublish(*, article: Article, editor: BaseUser, reason: str = "") -> Article:
    _check_editor(editor)

    if article.status != Article.Status.PUBLISHED:
        raise ApplicationError("Seul un article publié peut être dépublié.")

    article.status = Article.Status.UNPUBLISHED
    article.unpublished_at = timezone.now()
    article.unpublished_by = editor
    article.unpublish_reason = reason
    article.save(
        update_fields=[
            "status", "unpublished_at", "unpublished_by", "unpublish_reason", "updated_at"
        ]
    )
    return article


@transaction.atomic
def article_delete(*, article: Article, editor: BaseUser) -> None:
    _check_editor(editor)

    if article.status == Article.Status.PUBLISHED:
        raise ApplicationError(
            "Un article publié ne peut pas être supprimé. Dépubliez-le d'abord."
        )
    article.delete()


@transaction.atomic
def article_increment_views(*, article: Article) -> None:
    Article.objects.filter(pk=article.pk).update(views_count=models.F("views_count") + 1)

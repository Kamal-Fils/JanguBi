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
    """Autorité de niveau évêque : pastoral_role évêque/archevêque, OU admin
    diocèse-et-plus — par ``user.role`` OU par une RoleAssignment diocèse/province
    (source de vérité). Utilisé pour la publication des lettres pastorales."""
    from apps.users.scoping import accessible_diocese_ids, is_global_admin

    if user.pastoral_role in _BISHOP_PASTORAL_ROLES:
        return True
    if user.role in _BISHOP_ADMIN_ROLES:
        return True
    if is_global_admin(user):
        return True
    return bool(accessible_diocese_ids(user))


def is_news_editor(user: BaseUser) -> bool:
    """Peut créer/gérer un article : admin digital (user.role OU RoleAssignment)
    OU clergé (diacre inclus). L'autorité territoriale fine est vérifiée à part."""
    from apps.users.scoping import is_any_admin

    return is_any_admin(user) or user.pastoral_role in _CLERGY_EDITOR_ROLES


def _check_editor(user: BaseUser) -> None:
    if not is_news_editor(user):
        raise ApplicationError("Seuls les administrateurs et le clergé peuvent gérer les articles.")


def article_can_publish(*, user: BaseUser, article: Article) -> bool:
    from apps.users.scoping import is_any_admin

    if article.content_type == Article.ContentType.PASTORAL_LETTER:
        return is_bishop(user)
    # Diacre = brouillon seulement (matrice §16), même s'il détient une capacité
    # admin : la publication reste réservée au curé qui valide.
    if user.pastoral_role == PastoralRole.DIACRE:
        return False
    # ANNOUNCEMENT et ARTICLE : admin digital (role OU RoleAssignment) OU clergé
    # publicateur. Le « où » est tranché par _check_scope_authority.
    return is_any_admin(user) or user.pastoral_role in _CLERGY_PUBLISHER_ROLES


def _check_scope_consistency(
    scope_type: str,
    scope_parish_id: int | None,
    scope_diocese_id: int | None,
    scope_church_id: int | None = None,
) -> None:
    if scope_type == Article.ScopeType.PARISH and not scope_parish_id:
        raise ApplicationError("Un article de portée 'paroisse' doit avoir un scope_parish_id.")
    if scope_type == Article.ScopeType.DIOCESE and not scope_diocese_id:
        raise ApplicationError("Un article de portée 'diocèse' doit avoir un scope_diocese_id.")
    if scope_type == Article.ScopeType.CHURCH and not scope_church_id:
        raise ApplicationError("Un article de portée 'église' doit avoir un scope_church_id.")
    if scope_type == Article.ScopeType.GLOBAL and (
        scope_parish_id or scope_diocese_id or scope_church_id
    ):
        raise ApplicationError(
            "Un article global ne doit pas avoir de scope_parish_id, scope_diocese_id "
            "ou scope_church_id."
        )


def _resolve_scope_targets(
    *,
    scope_parish_id: int | None,
    scope_diocese_id: int | None,
    scope_church_id: int | None,
):
    """Résout les ids de portée (INT, contrat API inchangé) en instances FK.
    Erreur claire si l'entité n'existe pas — jamais de FK fantôme."""
    from apps.org.models import Church, Diocese, Parish

    parish = diocese = church = None
    if scope_parish_id is not None:
        parish = Parish.objects.filter(pk=scope_parish_id).first()
        if parish is None:
            raise ApplicationError("Paroisse introuvable.")
    if scope_diocese_id is not None:
        diocese = Diocese.objects.filter(pk=scope_diocese_id).first()
        if diocese is None:
            raise ApplicationError("Diocèse introuvable.")
    if scope_church_id is not None:
        church = Church.objects.filter(pk=scope_church_id).first()
        if church is None:
            raise ApplicationError("Église introuvable.")
    return parish, diocese, church


def _check_scope_authority(
    *,
    user: BaseUser,
    scope_type: str,
    scope_parish_id: int | None,
    scope_diocese_id: int | None,
    scope_church_id: int | None = None,
) -> None:
    """L'auteur/éditeur doit avoir autorité territoriale RÉELLE (RoleAssignment)
    sur la portée de l'article. Ferme l'injection inter-paroisses/diocèses/églises :
    un curé de la paroisse A ne peut ni créer ni publier un article scopé sur B, et
    un clergé sans affectation ne peut rien publier de scopé. L'autorité « église »
    découle de l'autorité sur la paroisse de cette église.
    """
    from apps.users.scoping import (
        accessible_province_ids,
        is_global_admin,
        user_can_admin_diocese,
        user_can_admin_parish,
    )

    if scope_type == Article.ScopeType.PARISH:
        if not user_can_admin_parish(user, scope_parish_id):
            raise ApplicationError("Vous n'avez pas autorité sur cette paroisse.")
    elif scope_type == Article.ScopeType.CHURCH:
        from apps.org.models import Church

        church = Church.objects.filter(pk=scope_church_id).first()
        if church is None:
            raise ApplicationError("Église introuvable.")
        if not user_can_admin_parish(user, church.parish_id):
            raise ApplicationError("Vous n'avez pas autorité sur cette église.")
    elif scope_type == Article.ScopeType.DIOCESE:
        if not user_can_admin_diocese(user, scope_diocese_id):
            raise ApplicationError("Vous n'avez pas autorité sur ce diocèse.")
    else:  # GLOBAL — réservé aux administrateurs province / national.
        if not (is_global_admin(user) or accessible_province_ids(user)):
            raise ApplicationError(
                "La portée globale est réservée aux administrateurs province ou national."
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
    scope_church_id: int | None = None,
) -> Article:
    _check_editor(author)
    _check_scope_consistency(scope_type, scope_parish_id, scope_diocese_id, scope_church_id)
    _check_scope_authority(
        user=author,
        scope_type=scope_type,
        scope_parish_id=scope_parish_id,
        scope_diocese_id=scope_diocese_id,
        scope_church_id=scope_church_id,
    )

    # Contrat API inchangé : ids reçus en INT, résolus en FK ici.
    scope_parish, scope_diocese, scope_church = _resolve_scope_targets(
        scope_parish_id=scope_parish_id,
        scope_diocese_id=scope_diocese_id,
        scope_church_id=scope_church_id,
    )

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

    scope_id = {
        Article.ScopeType.PARISH: scope_parish_id,
        Article.ScopeType.DIOCESE: scope_diocese_id,
        Article.ScopeType.CHURCH: scope_church_id,
    }.get(scope_type)
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
        scope_parish=scope_parish,
        scope_diocese=scope_diocese,
        scope_church=scope_church,
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
    # Autorité territoriale sur la portée réelle de l'article (anti inter-paroisses).
    _check_scope_authority(
        user=editor,
        scope_type=article.scope_type,
        scope_parish_id=article.scope_parish_id,
        scope_diocese_id=article.scope_diocese_id,
        scope_church_id=article.scope_church_id,
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

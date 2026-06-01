from django.db.models import QuerySet

from apps.news.models import Article, ArticleCategory
from apps.users.models import BaseUser


def category_list(*, active_only: bool = True) -> QuerySet[ArticleCategory]:
    qs = ArticleCategory.objects.all()
    if active_only:
        qs = qs.filter(is_active=True)
    return qs.order_by("display_order", "name")


def article_list(
    *,
    scope_type: str | None = None,
    scope_parish_id: int | None = None,
    scope_diocese_id: int | None = None,
    category_slug: str | None = None,
    status: str = Article.Status.PUBLISHED,
    author: BaseUser | None = None,
    search: str | None = None,
) -> QuerySet[Article]:
    qs = Article.objects.select_related("category", "author", "cover_image")

    if status:
        qs = qs.filter(status=status)
    if scope_type:
        qs = qs.filter(scope_type=scope_type)
    if scope_parish_id is not None:
        qs = qs.filter(scope_parish_id=scope_parish_id)
    if scope_diocese_id is not None:
        qs = qs.filter(scope_diocese_id=scope_diocese_id)
    if category_slug:
        qs = qs.filter(category__slug=category_slug)
    if author is not None:
        qs = qs.filter(author=author)
    if search:
        qs = qs.filter(title__icontains=search)

    return qs.order_by("-published_at", "-created_at")


def article_list_global(
    *,
    category_slug: str | None = None,
    search: str | None = None,
) -> QuerySet[Article]:
    """Articles publiés de portée globale — accessibles publiquement."""
    return article_list(
        scope_type=Article.ScopeType.GLOBAL,
        category_slug=category_slug,
        search=search,
    )


def article_list_for_parish(
    *,
    parish_id: int,
    category_slug: str | None = None,
    search: str | None = None,
) -> QuerySet[Article]:
    """Articles publiés d'une paroisse précise."""
    return article_list(
        scope_type=Article.ScopeType.PARISH,
        scope_parish_id=parish_id,
        category_slug=category_slug,
        search=search,
    )


def article_list_for_diocese(
    *,
    diocese_id: int,
    category_slug: str | None = None,
    search: str | None = None,
) -> QuerySet[Article]:
    """Articles publiés d'un diocèse précis."""
    return article_list(
        scope_type=Article.ScopeType.DIOCESE,
        scope_diocese_id=diocese_id,
        category_slug=category_slug,
        search=search,
    )


def article_get(*, article_id: str) -> Article | None:
    try:
        return Article.objects.select_related(
            "category", "author", "author__profile", "cover_image", "unpublished_by"
        ).get(pk=article_id)
    except Article.DoesNotExist:
        return None


def article_get_by_slug(*, slug: str) -> Article | None:
    try:
        return Article.objects.select_related(
            "category", "author", "author__profile", "cover_image", "unpublished_by"
        ).get(slug=slug)
    except Article.DoesNotExist:
        return None


def article_list_for_user(*, user: BaseUser) -> QuerySet[Article]:
    """Articles publiés visibles par l'utilisateur selon ses appartenances
    (multi-appartenance, Chantier 3a) : agrégation global ∪ église ∪ paroisse ∪
    diocèse via le helper générique get_scoped_queryset."""
    from apps.users.scoping import get_scoped_queryset

    qs = Article.objects.select_related("category", "author", "cover_image").filter(
        status=Article.Status.PUBLISHED
    )
    return get_scoped_queryset(qs, user).order_by("-published_at", "-created_at")

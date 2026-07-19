from django.db.models import QuerySet

from apps.tv.models import Category, Video


def category_list(*, include_clergy_only: bool = False) -> QuerySet[Category]:
    """Les catégories visibles par l'appelant.

    Le paramètre s'appelle ``include_clergy_only`` comme dans les trois autres
    selectors : il ÉLARGIT la vue au catalogue réservé, il ne la restreint pas.
    L'ancien nom ``clergy_only`` se lisait exactement à l'envers, sur le
    paramètre même qui porte le cloisonnement.
    """
    qs = Category.objects.all().order_by("order", "name")
    if not include_clergy_only:
        qs = qs.filter(is_clergy_only=False)
    return qs


def category_get_by_slug(*, slug: str, include_clergy_only: bool = True) -> Category | None:
    """Une catégorie par slug.

    ``include_clergy_only=False`` applique le même cloisonnement que la liste :
    sans ce garde-fou, un accès direct par slug contournerait la restriction
    clergé que ``category_list`` applique.
    """
    qs = Category.objects.filter(slug=slug)
    if not include_clergy_only:
        qs = qs.filter(is_clergy_only=False)
    return qs.first()


def video_get_by_id(*, video_id: int, include_clergy_only: bool = True) -> Video | None:
    """Une vidéo par id, avec le même cloisonnement clergé que ``video_list`` :
    une vidéo de catégorie réservée ne doit pas être atteignable en devinant son
    id depuis la route de détail."""
    qs = Video.objects.select_related("category").filter(id=video_id)
    if not include_clergy_only:
        qs = qs.filter(category__is_clergy_only=False)
    return qs.first()


def video_list(
    *,
    category_slug: str | None = None,
    is_live: str | None = None,
    is_pinned_live: str | None = None,
    include_clergy_only: bool = False,
) -> QuerySet[Video]:
    qs = Video.objects.select_related("category").all()

    if not include_clergy_only:
        qs = qs.filter(category__is_clergy_only=False)

    if category_slug:
        qs = qs.filter(category__slug=category_slug)

    if is_live in {"true", "false"}:
        qs = qs.filter(is_live=(is_live == "true"))

    if is_pinned_live in {"true", "false"}:
        qs = qs.filter(is_pinned_live=(is_pinned_live == "true"))

    return qs

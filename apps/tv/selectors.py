from django.db.models import QuerySet

from apps.tv.models import Category, Video


def category_list(*, clergy_only: bool = False) -> QuerySet[Category]:
    qs = Category.objects.all().order_by("order", "name")
    if not clergy_only:
        qs = qs.filter(is_clergy_only=False)
    return qs


def category_get_by_slug(*, slug: str) -> Category | None:
    return Category.objects.filter(slug=slug).first()


def video_get_by_id(*, video_id: int) -> Video | None:
    return Video.objects.select_related("category").filter(id=video_id).first()


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

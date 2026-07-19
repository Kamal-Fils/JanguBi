from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import QuerySet

if TYPE_CHECKING:  # seulement pour l'IDE/mypy
    from apps.bible.models import HomilieNote, ReadingPlan
    
def homilenote_list(*, author) -> QuerySet:
    from apps.bible.models import HomilieNote

    return (
        HomilieNote.objects.filter(author=author)
        .select_related("passage_start", "passage_end")
        .order_by("-created_at")
    )


def homilenote_get(*, note_id: int, user) -> "HomilieNote":
    from apps.bible.models import HomilieNote
    from apps.core.exceptions import ApplicationError

    try:
        return HomilieNote.objects.select_related("passage_start", "passage_end").get(
            pk=note_id, author=user
        )
    except HomilieNote.DoesNotExist:
        raise ApplicationError("Note introuvable.")


def lectio_divina_get_for_verse(*, user, passage_id: int):
    from apps.bible.models import LectioDivinaSession

    return LectioDivinaSession.objects.filter(user=user, passage_id=passage_id).first()


def lectio_divina_list(*, user) -> QuerySet:
    from apps.bible.models import LectioDivinaSession

    return LectioDivinaSession.objects.filter(user=user).select_related("passage").order_by("-updated_at")


def _annotate_is_subscribed(qs: QuerySet, user) -> QuerySet:
    """Ajoute `is_subscribed` en une sous-requête EXISTS (pas de N+1 en liste)."""
    from django.db.models import Exists, OuterRef, Value

    from apps.bible.models import ReadingPlanSubscription

    if user is None or not getattr(user, "is_authenticated", False):
        return qs.annotate(is_subscribed=Value(False))

    return qs.annotate(
        is_subscribed=Exists(
            ReadingPlanSubscription.objects.filter(plan=OuterRef("pk"), user=user)
        )
    )


def reading_plan_list(*, published_only: bool = True, user=None) -> QuerySet:
    from apps.bible.models import ReadingPlan

    qs = ReadingPlan.objects.select_related("author")
    if published_only:
        qs = qs.filter(is_published=True)
    return _annotate_is_subscribed(qs, user).order_by("-created_at")


def reading_plan_get(*, plan_id: int, user=None) -> "ReadingPlan":
    from apps.bible.models import ReadingPlan
    from apps.core.exceptions import ApplicationError

    qs = _annotate_is_subscribed(
        ReadingPlan.objects.prefetch_related("plan_passages__verse"), user
    )
    try:
        return qs.get(pk=plan_id)
    except ReadingPlan.DoesNotExist:
        raise ApplicationError("Plan de lecture introuvable.")

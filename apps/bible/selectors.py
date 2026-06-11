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


def reading_plan_list(*, published_only: bool = True) -> QuerySet:
    from apps.bible.models import ReadingPlan

    qs = ReadingPlan.objects.select_related("author")
    if published_only:
        qs = qs.filter(is_published=True)
    return qs.order_by("-created_at")


def reading_plan_get(*, plan_id: int) -> "ReadingPlan":
    from apps.bible.models import ReadingPlan
    from apps.core.exceptions import ApplicationError

    try:
        return ReadingPlan.objects.prefetch_related("plan_passages__verse").get(pk=plan_id)
    except ReadingPlan.DoesNotExist:
        raise ApplicationError("Plan de lecture introuvable.")

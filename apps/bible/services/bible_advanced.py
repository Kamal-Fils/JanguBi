from django.db import transaction

from apps.core.exceptions import ApplicationError


CLERGY_ROLES = {"diacre", "pretre", "eveque", "archeveque", "religieux"}
PRIEST_ROLES = {"pretre", "eveque", "archeveque"}


def _require_clergy(user) -> None:
    role = getattr(user, "pastoral_role", None)
    if role not in CLERGY_ROLES:
        raise ApplicationError("Réservé aux membres du clergé.")


def _require_priest_or_above(user) -> None:
    role = getattr(user, "pastoral_role", None)
    if role not in PRIEST_ROLES:
        raise ApplicationError("Réservé aux prêtres et évêques.")


@transaction.atomic
def homilenote_create(*, author, passage_start_id: int, content: str, passage_end_id: int | None = None):
    from apps.bible.models import HomilieNote, Verse

    _require_clergy(author)
    try:
        passage_start = Verse.objects.get(pk=passage_start_id)
    except Verse.DoesNotExist:
        raise ApplicationError("Verset de début introuvable.")
    passage_end = None
    if passage_end_id is not None:
        try:
            passage_end = Verse.objects.get(pk=passage_end_id)
        except Verse.DoesNotExist:
            raise ApplicationError("Verset de fin introuvable.")
    return HomilieNote.objects.create(
        author=author,
        passage_start=passage_start,
        passage_end=passage_end,
        content=content,
    )


@transaction.atomic
def homilenote_update(*, note, content: str):
    note.content = content
    note.save(update_fields=["content", "updated_at"])
    return note


@transaction.atomic
def homilenote_delete(*, note, user) -> None:
    if note.author_id != user.pk:
        raise ApplicationError("Vous ne pouvez supprimer que vos propres notes.")
    note.delete()


@transaction.atomic
def lectio_divina_upsert(*, user, passage_id: int, lectio: str = "", meditatio: str = "", oratio: str = "", contemplatio: str = ""):
    from apps.bible.models import LectioDivinaSession, Verse

    try:
        passage = Verse.objects.get(pk=passage_id)
    except Verse.DoesNotExist:
        raise ApplicationError("Verset introuvable.")
    session, _ = LectioDivinaSession.objects.update_or_create(
        user=user,
        passage=passage,
        defaults={
            "lectio": lectio,
            "meditatio": meditatio,
            "oratio": oratio,
            "contemplatio": contemplatio,
        },
    )
    return session


@transaction.atomic
def reading_plan_create(*, author, title: str, description: str = ""):
    from apps.bible.models import ReadingPlan

    _require_priest_or_above(author)
    return ReadingPlan.objects.create(author=author, title=title, description=description)


@transaction.atomic
def reading_plan_publish(*, plan, user):
    if plan.author_id != user.pk:
        raise ApplicationError("Vous ne pouvez publier que vos propres plans.")
    plan.is_published = True
    plan.save(update_fields=["is_published", "updated_at"])
    return plan

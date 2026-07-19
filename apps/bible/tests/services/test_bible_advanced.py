"""
Tests des services apps/bible/services/bible_advanced.py — HackSoft Styleguide.
Pattern AAA (Arrange / Act / Assert).

Verrouille deux contrats front ↔ back :
  - Lectio Divina : sauvegarde possible SANS verset (« lecture du jour ») ;
  - Parcours de lecture : inscription / désinscription idempotentes.
"""

import pytest
from django.utils import timezone

from apps.bible.models import (
    Book,
    Chapter,
    LectioDivinaSession,
    ReadingPlan,
    ReadingPlanSubscription,
    Testament,
    Verse,
)
from apps.bible.services.bible_advanced import (
    lectio_divina_upsert,
    reading_plan_subscribe,
    reading_plan_unsubscribe,
)
from apps.core.exceptions import ApplicationError
from apps.users.tests.factories import BaseUserFactory


@pytest.fixture
def verse(db):
    testament = Testament.objects.create(slug="at-svc", name="AT Service", order=98)
    book = Book.objects.create(name="ServiceBook", slug="service-book", testament=testament, order=98)
    chapter = Chapter.objects.create(book=book, number=1)
    return Verse.objects.create(chapter=chapter, number=1, text="Au commencement")


# ---------------------------------------------------------------------------
# lectio_divina_upsert — avec verset
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_lectio_upsert_creates_session_bound_to_verse(verse):
    # Arrange
    user = BaseUserFactory()

    # Act
    session = lectio_divina_upsert(user=user, passage_id=verse.pk, lectio="Je lis")

    # Assert
    assert session.passage_id == verse.pk
    assert session.lectio == "Je lis"


@pytest.mark.django_db
def test_lectio_upsert_updates_existing_session_for_same_verse(verse):
    # Arrange
    user = BaseUserFactory()
    lectio_divina_upsert(user=user, passage_id=verse.pk, lectio="Version 1")

    # Act
    session = lectio_divina_upsert(user=user, passage_id=verse.pk, lectio="Version 2")

    # Assert — mise à jour, pas de doublon
    assert session.lectio == "Version 2"
    assert LectioDivinaSession.objects.filter(user=user, passage=verse).count() == 1


@pytest.mark.django_db
def test_lectio_upsert_raises_when_verse_does_not_exist(db):
    # Arrange
    user = BaseUserFactory()

    # Act & Assert
    with pytest.raises(ApplicationError) as exc_info:
        lectio_divina_upsert(user=user, passage_id=999_999, lectio="x")

    assert "introuvable" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# lectio_divina_upsert — SANS verset (« lecture du jour »)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_lectio_upsert_without_passage_creates_daily_session(db):
    """CONTRAT : sauvegarde sans verset — le client envoie `null` (ou omet le champ)."""
    # Arrange
    user = BaseUserFactory()

    # Act
    session = lectio_divina_upsert(user=user, passage_id=None, meditatio="Je médite")

    # Assert
    assert session.passage_id is None
    assert session.session_date == timezone.localdate()
    assert session.meditatio == "Je médite"


@pytest.mark.django_db
def test_lectio_upsert_accepts_zero_as_no_passage(db):
    """RÉGRESSION : le client web envoie historiquement `passage_id=0` pour
    « lecture du jour ». Cette convention renvoyait 400 « Verset introuvable »."""
    # Arrange
    user = BaseUserFactory()

    # Act
    session = lectio_divina_upsert(user=user, passage_id=0, lectio="Lecture du jour")

    # Assert
    assert session.passage_id is None
    assert session.lectio == "Lecture du jour"


@pytest.mark.django_db
def test_lectio_upsert_without_passage_is_idempotent_within_the_same_day(db):
    # Arrange
    user = BaseUserFactory()
    lectio_divina_upsert(user=user, passage_id=None, lectio="Premier jet")

    # Act
    session = lectio_divina_upsert(user=user, passage_id=None, lectio="Second jet")

    # Assert — une seule ligne pour le jour courant
    assert session.lectio == "Second jet"
    assert LectioDivinaSession.objects.filter(user=user, passage__isnull=True).count() == 1


@pytest.mark.django_db
def test_lectio_upsert_without_passage_does_not_collide_between_users(db):
    # Arrange
    user_a, user_b = BaseUserFactory(), BaseUserFactory()

    # Act
    lectio_divina_upsert(user=user_a, passage_id=None, lectio="A")
    lectio_divina_upsert(user=user_b, passage_id=None, lectio="B")

    # Assert — chaque fidèle a sa propre session du jour
    assert LectioDivinaSession.objects.filter(passage__isnull=True).count() == 2


@pytest.mark.django_db
def test_lectio_upsert_without_passage_does_not_touch_verse_bound_session(verse):
    # Arrange
    user = BaseUserFactory()
    lectio_divina_upsert(user=user, passage_id=verse.pk, lectio="Sur le verset")

    # Act
    lectio_divina_upsert(user=user, passage_id=None, lectio="Sur la lecture du jour")

    # Assert — deux sessions distinctes coexistent
    assert LectioDivinaSession.objects.filter(user=user).count() == 2
    bound = LectioDivinaSession.objects.get(user=user, passage=verse)
    assert bound.lectio == "Sur le verset"


# ---------------------------------------------------------------------------
# reading_plan_subscribe / unsubscribe
# ---------------------------------------------------------------------------


@pytest.fixture
def published_plan(db):
    author = BaseUserFactory()
    return ReadingPlan.objects.create(author=author, title="Parcours Avent", is_published=True)


@pytest.mark.django_db
def test_reading_plan_subscribe_creates_subscription(published_plan):
    # Arrange
    user = BaseUserFactory()

    # Act
    reading_plan_subscribe(plan=published_plan, user=user)

    # Assert
    assert ReadingPlanSubscription.objects.filter(user=user, plan=published_plan).exists()


@pytest.mark.django_db
def test_reading_plan_subscribe_is_idempotent(published_plan):
    # Arrange
    user = BaseUserFactory()
    reading_plan_subscribe(plan=published_plan, user=user)

    # Act — seconde inscription
    reading_plan_subscribe(plan=published_plan, user=user)

    # Assert — pas de doublon (la contrainte unique n'est jamais violée)
    assert ReadingPlanSubscription.objects.filter(user=user, plan=published_plan).count() == 1


@pytest.mark.django_db
def test_reading_plan_subscribe_raises_when_plan_is_not_published(db):
    # Arrange
    author = BaseUserFactory()
    draft = ReadingPlan.objects.create(author=author, title="Brouillon", is_published=False)
    user = BaseUserFactory()

    # Act & Assert
    with pytest.raises(ApplicationError) as exc_info:
        reading_plan_subscribe(plan=draft, user=user)

    assert "publié" in str(exc_info.value).lower()
    assert not ReadingPlanSubscription.objects.filter(plan=draft).exists()


@pytest.mark.django_db
def test_reading_plan_unsubscribe_removes_subscription(published_plan):
    # Arrange
    user = BaseUserFactory()
    reading_plan_subscribe(plan=published_plan, user=user)

    # Act
    reading_plan_unsubscribe(plan=published_plan, user=user)

    # Assert
    assert not ReadingPlanSubscription.objects.filter(user=user, plan=published_plan).exists()


@pytest.mark.django_db
def test_reading_plan_unsubscribe_is_idempotent(published_plan):
    # Arrange — jamais inscrit
    user = BaseUserFactory()

    # Act & Assert — aucune exception
    reading_plan_unsubscribe(plan=published_plan, user=user)


@pytest.mark.django_db
def test_reading_plan_unsubscribe_does_not_affect_other_subscribers(published_plan):
    # Arrange
    user_a, user_b = BaseUserFactory(), BaseUserFactory()
    reading_plan_subscribe(plan=published_plan, user=user_a)
    reading_plan_subscribe(plan=published_plan, user=user_b)

    # Act
    reading_plan_unsubscribe(plan=published_plan, user=user_a)

    # Assert
    assert ReadingPlanSubscription.objects.filter(plan=published_plan).count() == 1
    assert ReadingPlanSubscription.objects.filter(user=user_b).exists()

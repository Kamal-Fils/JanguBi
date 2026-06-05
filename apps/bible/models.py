import logging
from typing import Optional

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.utils.text import slugify
from pgvector.django import HnswIndex, VectorField

from apps.common.models import BaseModel

logger = logging.getLogger(__name__)


class Testament(models.Model):
    """Ancien or Nouveau Testament."""

    slug = models.SlugField(max_length=32, unique=True)
    name = models.CharField(max_length=200)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self) -> str:
        return self.name


class Book(BaseModel):
    """A book of the Bible (e.g. Genèse, Psaumes, Matthieu)."""

    testament = models.ForeignKey(
        Testament,
        on_delete=models.PROTECT,
        related_name="books",
    )
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200)
    alt_names = models.JSONField(default=list, blank=True)
    order = models.IntegerField()
    verse_count = models.IntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Chapter(models.Model):
    """A chapter within a book."""

    book = models.ForeignKey(
        Book,
        on_delete=models.CASCADE,
        related_name="chapters",
    )
    number = models.IntegerField()
    name = models.CharField(max_length=255, blank=True, default="")
    verse_count = models.IntegerField(default=0)

    class Meta:
        unique_together = ("book", "number")
        ordering = ["number"]

    def __str__(self) -> str:
        return f"{self.book.name} {self.number}"


class Verse(models.Model):
    """A single verse within a chapter."""

    chapter = models.ForeignKey(
        Chapter,
        on_delete=models.CASCADE,
        related_name="verses",
    )
    number = models.IntegerField()
    text = models.TextField()
    original_id = models.IntegerField(null=True, blank=True)
    original_position = models.IntegerField(null=True, blank=True)
    source_file = models.CharField(max_length=128, blank=True, null=True)

    # Postgres full-text search vector
    tsv = SearchVectorField(null=True)

    # pgvector embedding — 768 dims (modèle local mpnet-base-v2, recherche
    # sémantique cosine). Vecteurs non normalisés => on interroge en cosine
    # (<=> / vector_cosine_ops), invariant à l'échelle.
    embedding = VectorField(dimensions=768, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("chapter", "number", "source_file")
        ordering = ["number"]
        indexes = [
            GinIndex(fields=["tsv"], name="idx_verse_tsv"),
            # Index ANN cosine pour la recherche vectorielle (top-k via <=>).
            HnswIndex(
                name="idx_verse_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]

    def __str__(self) -> str:
        return f"{self.chapter} : {self.number}"


class DailyText(BaseModel):
    """Daily readings fetched from the AELF API."""

    date = models.DateField(db_index=True)
    category = models.CharField(max_length=64)  # 'messe', 'heures', 'lecture'
    title = models.CharField(max_length=255, blank=True, default="")
    content = models.TextField()
    source_url = models.URLField(blank=True, null=True)

    # Cross-references to matched verses, populated by SearchService
    local_matches = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"{self.date} — {self.category}: {self.title[:50]}"


class HomilieNote(BaseModel):
    """Homily note linked to a Bible passage. Restricted to DIACRE and above."""

    author = models.ForeignKey(
        "users.BaseUser",
        on_delete=models.CASCADE,
        related_name="homilinotes",
    )
    passage_start = models.ForeignKey(
        Verse,
        on_delete=models.CASCADE,
        related_name="homilinote_starts",
    )
    passage_end = models.ForeignKey(
        Verse,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="homilinote_ends",
    )
    content = models.TextField()
    shared_with = models.ManyToManyField(
        "users.BaseUser",
        related_name="shared_homilinotes",
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Note d'homélie"
        verbose_name_plural = "Notes d'homélie"

    def __str__(self) -> str:
        return f"HomilieNote({self.author_id}, v{self.passage_start_id})"


class LectioDivinaSession(BaseModel):
    """Personal Lectio Divina session linked to a Bible verse."""

    user = models.ForeignKey(
        "users.BaseUser",
        on_delete=models.CASCADE,
        related_name="lectio_sessions",
    )
    passage = models.ForeignKey(
        Verse,
        on_delete=models.CASCADE,
        related_name="lectio_sessions",
    )
    lectio = models.TextField(blank=True)
    meditatio = models.TextField(blank=True)
    oratio = models.TextField(blank=True)
    contemplatio = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Session Lectio Divina"
        verbose_name_plural = "Sessions Lectio Divina"
        unique_together = [["user", "passage"]]

    def __str__(self) -> str:
        return f"LectioDivina({self.user_id}, v{self.passage_id})"


class ReadingPlan(BaseModel):
    """Curated Bible reading plan created by clergy."""

    author = models.ForeignKey(
        "users.BaseUser",
        on_delete=models.CASCADE,
        related_name="reading_plans",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_published = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Plan de lecture"
        verbose_name_plural = "Plans de lecture"

    def __str__(self) -> str:
        return f"ReadingPlan({self.title})"


class ReadingPlanPassage(BaseModel):
    """Ordered passage within a reading plan."""

    plan = models.ForeignKey(
        ReadingPlan,
        on_delete=models.CASCADE,
        related_name="plan_passages",
    )
    verse = models.ForeignKey(
        Verse,
        on_delete=models.CASCADE,
        related_name="plan_passages",
    )
    day_number = models.PositiveSmallIntegerField()
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["day_number", "order"]
        verbose_name = "Passage du plan"
        verbose_name_plural = "Passages du plan"

    def __str__(self) -> str:
        return f"PlanPassage(plan={self.plan_id}, day={self.day_number})"

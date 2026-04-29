import re
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils.text import slugify

from apps.common.models import BaseModel
from apps.tv.utils.youtube import build_embed_url, extract_youtube_video_id


class Category(BaseModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)



class Video(BaseModel):
    title = models.CharField(max_length=255, blank=True, default="")
    youtube_url = models.URLField()
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="videos")
    is_live = models.BooleanField(default=False)
    is_pinned_live = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_pinned_live", "-is_live", "-created_at"]
        indexes = [
            models.Index(fields=["category"]),
            models.Index(fields=["is_live"]),
            models.Index(fields=["is_pinned_live"]),
        ]

    def __str__(self) -> str:
        return self.title or self.youtube_url

    @property
    def youtube_id(self) -> str:
        return extract_youtube_video_id(self.youtube_url) or ""

    @property
    def embed_url(self) -> str:
        video_id = self.youtube_id
        if not video_id:
            return ""
        return build_embed_url(video_id)

    def clean(self):
        super().clean()
        video_id = extract_youtube_video_id(self.youtube_url)
        if not video_id:
            raise ValidationError({"youtube_url": "Invalid YouTube URL. Unable to extract a valid video ID."})
        if not re.match(r"^[A-Za-z0-9_-]{11}$", video_id):
            raise ValidationError({"youtube_url": "Invalid YouTube video ID format."})

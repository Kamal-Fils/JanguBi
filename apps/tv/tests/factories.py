import factory
from factory.django import DjangoModelFactory

from apps.tv.models import Category, Video


class CategoryFactory(DjangoModelFactory):
    name = factory.Sequence(lambda n: f"Category {n}")
    slug = factory.Sequence(lambda n: f"category-{n}")
    order = factory.Sequence(lambda n: n)

    class Meta:
        model = Category


class VideoFactory(DjangoModelFactory):
    title = factory.Sequence(lambda n: f"Video {n}")
    youtube_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    category = factory.SubFactory(CategoryFactory)
    is_live = False
    is_pinned_live = False

    class Meta:
        model = Video

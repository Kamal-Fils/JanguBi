"""
factory_boy factories for apps/rosary/ tests.
"""

import factory
from factory.django import DjangoModelFactory

from apps.rosary.models import Mystery, MysteryGroup, MysteryPrayer, Prayer, RosaryDay


class MysteryGroupFactory(DjangoModelFactory):
    name = factory.Sequence(lambda n: f"Mystery Group {n}")
    slug = factory.Sequence(lambda n: f"mystery-group-{n}")

    class Meta:
        model = MysteryGroup


class MysteryFactory(DjangoModelFactory):
    group = factory.SubFactory(MysteryGroupFactory)
    order = factory.Sequence(lambda n: (n % 5) + 1)
    title = factory.Sequence(lambda n: f"Mystery {n}")
    meditation = factory.Sequence(lambda n: f"Meditation text {n}")

    class Meta:
        model = Mystery


class PrayerFactory(DjangoModelFactory):
    type = Prayer.Type.OUR_FATHER
    text = factory.Sequence(lambda n: f"Prayer text {n}")
    language = "FR"

    class Meta:
        model = Prayer


class MysteryPrayerFactory(DjangoModelFactory):
    mystery = factory.SubFactory(MysteryFactory)
    prayer = factory.SubFactory(PrayerFactory)
    order = factory.Sequence(lambda n: n + 1)

    class Meta:
        model = MysteryPrayer


class RosaryDayFactory(DjangoModelFactory):
    weekday = factory.Sequence(lambda n: n % 7)
    group = factory.SubFactory(MysteryGroupFactory)

    class Meta:
        model = RosaryDay

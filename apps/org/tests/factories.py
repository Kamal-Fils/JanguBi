import factory
from factory.django import DjangoModelFactory

from apps.org.models import Diocese, Parish, Province, ReligiousOrder, ReligiousCommunity


class ProvinceFactory(DjangoModelFactory):
    class Meta:
        model = Province

    name = factory.Sequence(lambda n: f"Province {n}")
    code = factory.Sequence(lambda n: f"PR{n:02d}")
    country = "Senegal"


class DioceseFactory(DjangoModelFactory):
    class Meta:
        model = Diocese

    name = factory.Sequence(lambda n: f"Diocèse {n}")
    code = factory.Sequence(lambda n: f"DI{n:02d}")
    province = factory.SubFactory(ProvinceFactory)


class ParishFactory(DjangoModelFactory):
    class Meta:
        model = Parish

    name = factory.Sequence(lambda n: f"Paroisse {n}")
    diocese = factory.SubFactory(DioceseFactory)
    city = factory.Sequence(lambda n: f"Ville {n}")
    address = ""


class ReligiousOrderFactory(DjangoModelFactory):
    class Meta:
        model = ReligiousOrder

    name = factory.Sequence(lambda n: f"Ordre {n}")
    abbreviation = factory.Sequence(lambda n: f"OR{n}")


class ReligiousCommunityFactory(DjangoModelFactory):
    class Meta:
        model = ReligiousCommunity

    name = factory.Sequence(lambda n: f"Communauté {n}")
    order = factory.SubFactory(ReligiousOrderFactory)
    diocese = factory.SubFactory(DioceseFactory)
    parish = None

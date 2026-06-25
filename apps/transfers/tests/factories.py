import factory
from factory.django import DjangoModelFactory

from apps.org.tests.factories import ParishFactory
from apps.transfers.models import ParishTransferRequest


class ParishTransferRequestFactory(DjangoModelFactory):
    class Meta:
        model = ParishTransferRequest

    requester = factory.SubFactory('apps.users.tests.factories.BaseUserFactory')
    origin_parish = factory.SubFactory(ParishFactory)
    destination_parish = factory.SubFactory(ParishFactory)
    reason = ""

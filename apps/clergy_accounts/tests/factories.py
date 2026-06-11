from datetime import timedelta

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.clergy_accounts.models import ClergicalInvitation
from apps.org.tests.factories import DioceseFactory
from apps.users.enums import PastoralRole
from apps.users.tests.factories import BaseUserFactory


class ClergicalInvitationFactory(DjangoModelFactory):
    class Meta:
        model = ClergicalInvitation

    email = factory.Sequence(lambda n: f"clergy{n}@example.com")
    first_name = factory.Sequence(lambda n: f"Abbé{n}")
    last_name = factory.Sequence(lambda n: f"Sène{n}")
    pastoral_role = PastoralRole.PRETRE
    diocese = factory.SubFactory(DioceseFactory)
    created_by = factory.SubFactory(BaseUserFactory)
    status = ClergicalInvitation.Status.PENDING
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(hours=48))

"""
Factories factory_boy for emails app tests.
Aligned with apps/emails/models.py — Email model fields.
"""

import factory
from factory.django import DjangoModelFactory

from apps.emails.models import Email


class EmailFactory(DjangoModelFactory):
    """Creates a READY email by default."""

    class Meta:
        model = Email

    to = factory.Sequence(lambda n: f"recipient{n}@example.com")
    subject = factory.Sequence(lambda n: f"Subject {n}")
    html = factory.Sequence(lambda n: f"<p>HTML body {n}</p>")
    plain_text = factory.Sequence(lambda n: f"Plain text body {n}")
    status = Email.Status.READY


class SendingEmailFactory(EmailFactory):
    """Creates an email that is already in SENDING status."""

    status = Email.Status.SENDING


class SentEmailFactory(EmailFactory):
    """Creates an email that has already been SENT."""

    status = Email.Status.SENT


class FailedEmailFactory(EmailFactory):
    """Creates an email that is in FAILED status."""

    status = Email.Status.FAILED

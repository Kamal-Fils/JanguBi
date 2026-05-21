from celery import shared_task
from django.conf import settings


@shared_task(bind=True, max_retries=3)
def document_requests_auto_escalate(self):
    from apps.documents.services import document_request_run_escalation

    escalate_days = getattr(settings, "DOCS_ESCALATE_DAYS", 7)
    deposit_reminder_days = getattr(settings, "DOCS_DEPOSIT_REMINDER_DAYS", 3)
    requester_reminder_days = getattr(settings, "DOCS_REQUESTER_REMINDER_DAYS", 5)

    try:
        document_request_run_escalation(
            escalate_days=escalate_days,
            deposit_reminder_days=deposit_reminder_days,
            requester_reminder_days=requester_reminder_days,
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=3600)

from celery import shared_task
from django.conf import settings


@shared_task(bind=True, max_retries=3)
def purge_expired_unactivated_admin_accounts(self) -> int:
    """Delete admin accounts that were created but never activated within the expiry window."""
    from apps.users.services import purge_expired_unactivated_admin_accounts as _purge

    expiry_days = getattr(settings, "ADMIN_ACCOUNT_EXPIRY_DAYS", 7)
    try:
        return _purge(expiry_days=expiry_days)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=300)

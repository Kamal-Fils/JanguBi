from celery import shared_task
from django.conf import settings
from django.utils import timezone
from datetime import timedelta


@shared_task
def purge_expired_unactivated_admin_accounts() -> int:
    """Delete admin accounts that were created but never activated within the expiry window."""
    from apps.users.models import BaseUser
    from apps.users.enums import UserRole

    admin_roles = {
        UserRole.SUPER_ADMIN,
        UserRole.PROVINCE_ADMIN,
        UserRole.DIOCESE_ADMIN,
        UserRole.PARISH_ADMIN,
        UserRole.CHURCH_ADMIN,
    }
    expiry_days = getattr(settings, "ADMIN_ACCOUNT_EXPIRY_DAYS", 7)
    cutoff = timezone.now() - timedelta(days=expiry_days)

    qs = BaseUser.objects.filter(
        role__in=admin_roles,
        last_login__isnull=True,
        created_at__lt=cutoff,
    )
    count, _ = qs.delete()
    return count

from django.db.models import QuerySet, Sum
from django.utils import timezone

from .models import Donation, DonationCampaign


def campaign_list_active() -> QuerySet[DonationCampaign]:
    now = timezone.now()
    return DonationCampaign.objects.filter(
        is_active=True,
        starts_at__lte=now,
    ).filter(
        ends_at__isnull=True,
    ) | DonationCampaign.objects.filter(
        is_active=True,
        starts_at__lte=now,
        ends_at__gte=now,
    )


def donation_list_for_donor(*, donor) -> QuerySet[Donation]:
    return Donation.objects.filter(donor=donor).select_related("campaign")


def donation_dashboard_for_parish(*, parish_id: int) -> dict:
    qs = Donation.objects.filter(
        campaign__scope_type="parish",
        campaign__scope_id=parish_id,
        status="confirmed",
    )
    total = qs.aggregate(total=Sum("amount"))["total"] or 0
    return {"total": total, "count": qs.count()}

from django.db.models import Count, Q, QuerySet, Sum
from django.utils import timezone

from .models import Donation, DonationCampaign


def _parish_donations(parish_id: int) -> QuerySet[Donation]:
    """Dons confirmés rattachés à une paroisse (don direct, campagne FK, ou ancien scope_id)."""
    return Donation.objects.filter(status="confirmed").filter(
        Q(parish_id=parish_id)
        | Q(campaign__parish_id=parish_id)
        | Q(campaign__scope_type="parish", campaign__scope_id=parish_id)
    )


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
    qs = _parish_donations(parish_id)
    total = qs.aggregate(total=Sum("amount"))["total"] or 0
    return {"total": total, "count": qs.count()}


def donation_flow_for_parish(*, parish_id: int, since=None) -> dict:
    """Flux de dons d'une paroisse : total + ventilation par type (pour le dashboard curé)."""
    qs = _parish_donations(parish_id)
    if since is not None:
        qs = qs.filter(created_at__gte=since)
    total = qs.aggregate(total=Sum("amount"))["total"] or 0
    by_type = [
        {
            "donation_type": row["campaign__donation_type"] or "free_donation",
            "total": row["total"] or 0,
            "count": row["count"],
        }
        for row in qs.values("campaign__donation_type").annotate(
            total=Sum("amount"), count=Count("id")
        )
    ]
    return {"total": total, "count": qs.count(), "by_type": by_type}

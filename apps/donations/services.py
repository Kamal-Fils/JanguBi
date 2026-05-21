from django.db import transaction

from apps.core.exceptions import ApplicationError

from .models import Donation, DonationCampaign, DonationStatus


@transaction.atomic
def campaign_create(
    *,
    created_by,
    title: str,
    description: str = "",
    donation_type: str,
    target_amount=None,
    scope_type: str = "global",
    scope_id=None,
) -> DonationCampaign:
    from apps.users.enums import PastoralRole

    clergy_roles = {
        PastoralRole.PRETRE,
        PastoralRole.EVEQUE,
        PastoralRole.ARCHEVEQUE,
        PastoralRole.DIACRE,
    }
    if getattr(created_by, "pastoral_role", None) not in clergy_roles:
        raise ApplicationError("La création de campagne est réservée au clergé.")
    campaign = DonationCampaign.objects.create(
        created_by=created_by,
        title=title,
        description=description,
        donation_type=donation_type,
        target_amount=target_amount,
        scope_type=scope_type,
        scope_id=scope_id,
    )
    return campaign


@transaction.atomic
def donation_make(
    *,
    donor,
    campaign_id: int | None = None,
    amount,
    payment_provider: str,
    is_anonymous: bool = False,
    note: str = "",
    payment_reference: str = "",
) -> Donation:
    campaign = None
    if campaign_id is not None:
        try:
            campaign = DonationCampaign.objects.get(id=campaign_id, is_active=True)
        except DonationCampaign.DoesNotExist:
            raise ApplicationError("Campagne introuvable ou inactive.")

    donation = Donation.objects.create(
        donor=donor if not is_anonymous else None,
        campaign=campaign,
        amount=amount,
        payment_provider=payment_provider,
        payment_reference=payment_reference,
        is_anonymous=is_anonymous,
        note=note,
        status=DonationStatus.CONFIRMED,
    )
    return donation

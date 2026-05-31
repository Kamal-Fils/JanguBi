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
    parish_id=None,
    church_id=None,
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

    parish = church = None
    if church_id is not None:
        from apps.org.models import Church

        church = Church.objects.filter(id=church_id).select_related("parish").first()
        if church is None:
            raise ApplicationError("Église introuvable.")
        parish = church.parish
    elif parish_id is not None:
        from apps.org.models import Parish

        parish = Parish.objects.filter(id=parish_id).first()
        if parish is None:
            raise ApplicationError("Paroisse introuvable.")

    if parish is not None:
        # Cohérence avec l'ancien scope_type/scope_id (rétro-compatibilité).
        scope_type = "parish"
        scope_id = parish.id

    campaign = DonationCampaign.objects.create(
        created_by=created_by,
        title=title,
        description=description,
        donation_type=donation_type,
        target_amount=target_amount,
        scope_type=scope_type,
        scope_id=scope_id,
        parish=parish,
        church=church,
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
    parish_id: int | None = None,
) -> Donation:
    campaign = None
    if campaign_id is not None:
        try:
            campaign = DonationCampaign.objects.select_related("parish").get(
                id=campaign_id, is_active=True
            )
        except DonationCampaign.DoesNotExist:
            raise ApplicationError("Campagne introuvable ou inactive.")

    # Paroisse bénéficiaire : héritée de la campagne, sinon don direct à une paroisse.
    parish = None
    if campaign is not None and campaign.parish_id:
        parish = campaign.parish
    elif parish_id is not None:
        from apps.org.models import Parish

        parish = Parish.objects.filter(id=parish_id).first()

    donation = Donation.objects.create(
        donor=donor if not is_anonymous else None,
        campaign=campaign,
        parish=parish,
        amount=amount,
        payment_provider=payment_provider,
        payment_reference=payment_reference,
        is_anonymous=is_anonymous,
        note=note,
        status=DonationStatus.CONFIRMED,
    )
    return donation

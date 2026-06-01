from decimal import Decimal

from django.db import transaction

from apps.core.exceptions import ApplicationError

from .models import (
    DONATION_TERMINAL_STATUSES,
    Donation,
    DonationCampaign,
    DonationStatus,
    PaymentProvider,
)

ANONYMOUS_DONATION_MAX = Decimal("25000")

# Providers de paiement EN LIGNE — désactivés tant que l'IPN signé n'est pas livré
# (Chantier 5b). Le 5b retirera cette garde en branchant le webhook. Évite un don en
# ligne bloqué en PENDING indéfiniment ; le cash/manuel reste pleinement fonctionnel.
ONLINE_PAYMENT_PROVIDERS = frozenset(
    {
        PaymentProvider.WAVE,
        PaymentProvider.ORANGE_MONEY,
        PaymentProvider.FREE_MONEY,
    }
)


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


def _resolve_donation_target(*, donor, campaign, church_id, parish_id):
    """Étiquetage (B6a + RG-PAY-03). Renvoie (church, parish).

    Priorité : campagne → (church_id/parish_id explicites) → défaut = église/paroisse
    PRINCIPALE du donateur (Membership is_primary). RG-PAY-03 : si une église est
    renseignée, sa paroisse DOIT égaler la paroisse du don.
    """
    from apps.org.models import Church, Parish

    if campaign is not None and campaign.parish_id:
        return campaign.church, campaign.parish

    church = parish = None
    if church_id is not None:
        church = Church.objects.select_related("parish").filter(id=church_id).first()
        if church is None:
            raise ApplicationError("Église introuvable.")
    if parish_id is not None:
        parish = Parish.objects.filter(id=parish_id).first()
        if parish is None:
            raise ApplicationError("Paroisse introuvable.")

    if church is not None:
        # RG-PAY-03 : cohérence église ↔ paroisse.
        if parish is not None and church.parish_id != parish.id:
            raise ApplicationError(
                "L'église ne correspond pas à la paroisse du don (RG-PAY-03)."
            )
        parish = church.parish
    elif parish is None:
        # Défaut : église/paroisse principale du donateur (appartenance is_primary).
        from apps.users.models import Membership

        primary = (
            Membership.objects.filter(user=donor, is_primary=True)
            .select_related("church__parish")
            .first()
            if donor is not None
            else None
        )
        if primary is not None:
            church = primary.church
            parish = church.parish

    return church, parish


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
    church_id: int | None = None,
    anonymous_donor_name: str = "",
    anonymous_donor_phone: str = "",
) -> Donation:
    # Garde de transition : pas de paiement en ligne tant que l'IPN (5b) n'est pas
    # branché — sinon le don resterait PENDING indéfiniment (jamais confirmé).
    if payment_provider in ONLINE_PAYMENT_PROVIDERS:
        raise ApplicationError(
            "Le paiement en ligne sera bientôt disponible. Utilisez les espèces "
            "pour le moment."
        )

    campaign = None
    if campaign_id is not None:
        try:
            campaign = DonationCampaign.objects.select_related("parish", "church").get(
                id=campaign_id, is_active=True
            )
        except DonationCampaign.DoesNotExist:
            raise ApplicationError("Campagne introuvable ou inactive.")

    church, parish = _resolve_donation_target(
        donor=donor, campaign=campaign, church_id=church_id, parish_id=parish_id
    )

    # Anonymat (RG-PAY-01/02) : donor NULL XOR nom anonyme ; plafond 25 000 FCFA.
    if is_anonymous:
        if not anonymous_donor_name.strip():
            raise ApplicationError("Un don anonyme requiert un nom de donateur.")
        if Decimal(amount) > ANONYMOUS_DONATION_MAX:
            raise ApplicationError(
                "Un don anonyme ne peut excéder 25 000 FCFA."
            )
        effective_donor = None
    else:
        effective_donor = donor
        anonymous_donor_name = ""
        anonymous_donor_phone = ""

    # RG-PAY-04 : création TOUJOURS en PENDING (jamais confirmé d'office).
    donation = Donation.objects.create(
        donor=effective_donor,
        campaign=campaign,
        parish=parish,
        church=church,
        amount=amount,
        payment_provider=payment_provider,
        payment_reference=payment_reference,
        is_anonymous=is_anonymous,
        anonymous_donor_name=anonymous_donor_name,
        anonymous_donor_phone=anonymous_donor_phone,
        note=note,
        status=DonationStatus.PENDING,
    )
    return donation


@transaction.atomic
def donation_confirm(*, donation: Donation, payment_reference: str = "") -> Donation:
    """Confirmation manuelle V1 (cas ESPÈCES uniquement). PENDING → CONFIRMED,
    idempotent, jamais d'écrasement d'un état terminal.

    RESTRICTION RG-PAY : les providers EN LIGNE (wave/orange_money/free) ne sont PAS
    confirmables manuellement — réservé à l'IPN signé (Chantier 5b). L'autorité
    territoriale est vérifiée par l'API appelante.
    """
    if donation.payment_provider != PaymentProvider.CASH:
        raise ApplicationError(
            "Confirmation manuelle réservée aux dons en espèces ; les paiements en "
            "ligne sont confirmés par le webhook du prestataire."
        )

    if donation.status == DonationStatus.CONFIRMED:
        return donation  # idempotent

    if donation.status in DONATION_TERMINAL_STATUSES:
        raise ApplicationError(
            f"Impossible de confirmer un don dans l'état terminal « {donation.status} »."
        )

    donation.status = DonationStatus.CONFIRMED
    update_fields = ["status", "updated_at"]
    if payment_reference:
        donation.payment_reference = payment_reference
        update_fields.append("payment_reference")
    donation.save(update_fields=update_fields)
    return donation

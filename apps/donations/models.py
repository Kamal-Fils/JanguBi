from django.db import models
from django.db.models import Q
from django.utils import timezone


class DonationType(models.TextChoices):
    SUNDAY_COLLECTION = "sunday_collection", "Quête du dimanche"
    CHURCH_TITHE = "church_tithe", "Denier de l'Église"
    MASS_INTENTION_OFFERING = "mass_intention_offering", "Offrande de messe"
    SPECIAL_PROJECT = "special_project", "Projet spécial"
    FREE_DONATION = "free_donation", "Don libre"


class PaymentProvider(models.TextChoices):
    WAVE = "wave", "Wave"
    ORANGE_MONEY = "orange_money", "Orange Money"
    FREE_MONEY = "free_money", "Free Money"
    CASH = "cash", "Espèces"


class DonationStatus(models.TextChoices):
    PENDING = "pending", "En attente"
    CONFIRMED = "confirmed", "Confirmé"  # terminal succès (le « completed » du domaine)
    FAILED = "failed", "Échoué"
    CANCELED = "canceled", "Annulé"
    REFUNDED = "refunded", "Remboursé"


# États terminaux : un don jamais ré-ouvert une fois ici (RG-PAY-04).
DONATION_TERMINAL_STATUSES = frozenset(
    {
        DonationStatus.CONFIRMED,
        DonationStatus.FAILED,
        DonationStatus.CANCELED,
        DonationStatus.REFUNDED,
    }
)


class DonationCampaign(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    donation_type = models.CharField(choices=DonationType.choices, max_length=40)
    target_amount = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True)
    currency = models.CharField(max_length=3, default="XOF")
    scope_type = models.CharField(max_length=20, default="global")
    scope_id = models.IntegerField(null=True, blank=True)
    # FK territoriales réelles (remplacent progressivement scope_type/scope_id).
    parish = models.ForeignKey(
        "org.Parish",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="donation_campaigns",
    )
    church = models.ForeignKey(
        "org.Church",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="donation_campaigns",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        "users.BaseUser",
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_campaigns",
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"DonationCampaign({self.id}) — {self.title}"


class Donation(models.Model):
    donor = models.ForeignKey(
        "users.BaseUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="donations",
    )
    campaign = models.ForeignKey(
        DonationCampaign,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="donations",
    )
    # Paroisse bénéficiaire (déduite de la campagne, ou directe pour un don libre).
    parish = models.ForeignKey(
        "org.Parish",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="donations",
    )
    # Église bénéficiaire (étiquetage RG-PAY-03 : church.parish == parish).
    church = models.ForeignKey(
        "org.Church",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="donations",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=0)
    currency = models.CharField(max_length=3, default="XOF")
    payment_provider = models.CharField(choices=PaymentProvider.choices, max_length=20)
    payment_reference = models.CharField(max_length=200, blank=True)
    status = models.CharField(
        choices=DonationStatus.choices,
        max_length=20,
        default=DonationStatus.PENDING,
        db_index=True,
    )
    is_anonymous = models.BooleanField(default=False)
    # Don anonyme : donor IS NULL, identité libre conservée ici (RG-PAY-01/02).
    anonymous_donor_name = models.CharField(max_length=120, blank=True, default="")
    anonymous_donor_phone = models.CharField(max_length=30, blank=True, default="")
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # RG-PAY-01/02 : un don est SOIT attribué (donor renseigné, pas de nom
            # anonyme) SOIT anonyme (donor NULL, nom anonyme renseigné). XOR strict.
            models.CheckConstraint(
                name="donation_donor_xor_anonymous",
                condition=(
                    Q(donor__isnull=False) & Q(anonymous_donor_name="")
                )
                | (Q(donor__isnull=True) & ~Q(anonymous_donor_name="")),
            ),
        ]

    def __str__(self) -> str:
        return f"Donation({self.id}) — {self.amount} {self.currency} — {self.status}"

    def delete(self, *args, **kwargs):
        # Registre financier immuable : un don ne se supprime pas (RG-PAY-05).
        from apps.core.exceptions import ApplicationError

        raise ApplicationError("Un don ne peut pas être supprimé (registre financier).")

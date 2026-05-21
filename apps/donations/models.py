from django.db import models
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
    CONFIRMED = "confirmed", "Confirmé"
    FAILED = "failed", "Échoué"
    REFUNDED = "refunded", "Remboursé"


class DonationCampaign(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    donation_type = models.CharField(choices=DonationType.choices, max_length=40)
    target_amount = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True)
    currency = models.CharField(max_length=3, default="XOF")
    scope_type = models.CharField(max_length=20, default="global")
    scope_id = models.IntegerField(null=True, blank=True)
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
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Donation({self.id}) — {self.amount} {self.currency} — {self.status}"

from django.db import models
from django.utils import timezone


class MassIntentionType(models.TextChoices):
    FOR_DECEASED = "for_deceased", "Pour un défunt"
    FOR_LIVING = "for_living", "Pour un vivant"
    FOR_OCCASION = "for_occasion", "Pour une occasion"
    FOR_COMMUNITY = "for_community", "Pour la communauté"


class MassIntentionStatus(models.TextChoices):
    PENDING = "pending", "En attente"
    ACCEPTED = "accepted", "Acceptée"
    DATE_PROPOSED = "date_proposed", "Date proposée"
    CONFIRMED = "confirmed", "Confirmée"
    CELEBRATED = "celebrated", "Célébrée"
    DECLINED = "declined", "Refusée"


class MassIntention(models.Model):
    requestor = models.ForeignKey(
        "users.BaseUser",
        on_delete=models.CASCADE,
        related_name="mass_intentions",
    )
    pretre = models.ForeignKey(
        "users.BaseUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="received_intentions",
    )
    parish = models.ForeignKey(
        "org.Parish",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="mass_intentions",
    )
    intention_type = models.CharField(choices=MassIntentionType.choices, max_length=30)
    intention_text = models.TextField()
    status = models.CharField(
        choices=MassIntentionStatus.choices,
        max_length=20,
        default=MassIntentionStatus.PENDING,
        db_index=True,
    )
    proposed_date = models.DateField(null=True, blank=True)
    celebration_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"MassIntention({self.id}) — {self.intention_type} — {self.status}"

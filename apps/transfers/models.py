from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class TransferStatus(models.TextChoices):
    PENDING = "pending", _("En attente")
    APPROVED_BY_ORIGIN = "approved_by_origin", _("Approuvée par la paroisse d'origine")
    ACKNOWLEDGED_BY_DESTINATION = (
        "acknowledged_by_destination",
        _("Accusée par la paroisse de destination"),
    )
    COMPLETED = "completed", _("Finalisée")
    REJECTED = "rejected", _("Rejetée")


class ParishTransferRequest(models.Model):
    """
    Demande de transfert paroissial d'un fidèle.

    Cycle de vie :
        pending → approved_by_origin → completed
        pending → rejected
        approved_by_origin → rejected

    Le statut terminal ``completed`` est posé par la paroisse de destination
    (accusé de réception) et déclenche le déplacement de l'appartenance principale
    du demandeur vers la paroisse de destination.
    """

    requester = models.ForeignKey(
        "users.BaseUser",
        verbose_name=_("demandeur"),
        on_delete=models.CASCADE,
        related_name="transfer_requests",
    )
    origin_parish = models.ForeignKey(
        "org.Parish",
        verbose_name=_("paroisse d'origine"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="outgoing_transfers",
    )
    destination_parish = models.ForeignKey(
        "org.Parish",
        verbose_name=_("paroisse de destination"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="incoming_transfers",
    )
    status = models.CharField(
        _("statut"),
        choices=TransferStatus.choices,
        max_length=30,
        default=TransferStatus.PENDING,
        db_index=True,
    )
    reason = models.TextField(_("motif"), blank=True, default="")
    rejection_reason = models.TextField(_("motif de rejet"), blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("demande de transfert paroissial")
        verbose_name_plural = _("demandes de transfert paroissial")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"ParishTransferRequest({self.id}) — {self.requester_id} — {self.status}"

import secrets
from datetime import date

from django.db import models
from django.utils import timezone


def generate_intention_reference() -> str:
    """Référence publique d'une intention — ``INT-YYYYMMDD-XXXXXXXX``.

    Utilisée comme identifiant du reçu numérique remis au fidèle : c'est ce
    qu'il cite au secrétariat. Elle est donc générée pour TOUTE intention, y
    compris celles créées hors service (tests, commande de gestion, admin), d'où
    le ``default=`` sur le champ plutôt qu'une affectation dans le service.

    ``token_hex(4)`` (4,2 milliards de valeurs par jour) rend la collision
    négligeable, et ``unique=True`` la transforme de toute façon en erreur
    franche plutôt qu'en confusion entre deux reçus.
    """
    return f"INT-{date.today().strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}"


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
    reference = models.CharField(
        max_length=32,
        unique=True,
        default=generate_intention_reference,
        help_text="Référence publique citée sur le reçu numérique.",
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
    # Reçu numérique — PROTECT : le reçu est la trace que le fidèle est venu
    # chercher, il ne doit pas disparaître par effet de bord d'une purge de
    # fichiers. Renseigné à la célébration, régénérable à la demande.
    receipt_file = models.ForeignKey(
        "files.File",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="mass_intention_receipts",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"MassIntention({self.id}) — {self.reference} — {self.status}"


class MassIntentionStatusLog(models.Model):
    """Journal immuable des changements de statut d'une intention.

    Même rôle que ``DocumentRequestStatusLog`` (``apps/documents``) : une
    intention de messe engage la parole du prêtre envers un fidèle, souvent
    autour d'un deuil. Quand le fidèle demande « où en est mon intention ? »
    ou conteste une date, il faut pouvoir dire qui a fait quoi et quand —
    ``updated_at`` seul ne garde que la dernière écriture et perd l'historique.

    Écrit uniquement par ``_log_status_change`` (services.py) : aucune mise à
    jour ni suppression n'est prévue.
    """

    intention = models.ForeignKey(
        MassIntention,
        on_delete=models.CASCADE,
        related_name="status_logs",
    )
    from_status = models.CharField(max_length=20, blank=True, default="")
    to_status = models.CharField(max_length=20)
    changed_by = models.ForeignKey(
        "users.BaseUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="mass_intention_status_changes",
    )
    comment = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["intention", "created_at"], name="massint_log_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.intention_id}: {self.from_status} → {self.to_status}"

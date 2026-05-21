import uuid

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel


class ClergicalInvitation(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", _("En attente")
        ACCEPTED = "accepted", _("Acceptée")
        REVOKED = "revoked", _("Révoquée")
        EXPIRED = "expired", _("Expirée")

    token = models.UUIDField(
        _("token"),
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
    )
    email = models.EmailField(_("email"))
    first_name = models.CharField(_("prénom"), max_length=150)
    last_name = models.CharField(_("nom"), max_length=150)

    pastoral_role = models.CharField(
        _("rôle pastoral"),
        max_length=20,
    )

    diocese = models.ForeignKey(
        "org.Diocese",
        verbose_name=_("diocèse"),
        on_delete=models.PROTECT,
        related_name="clergy_invitations",
        null=True,
        blank=True,
    )

    created_by = models.ForeignKey(
        "users.BaseUser",
        verbose_name=_("créé par"),
        on_delete=models.SET_NULL,
        null=True,
        related_name="sent_clergy_invitations",
    )

    accepted_by = models.ForeignKey(
        "users.BaseUser",
        verbose_name=_("accepté par"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accepted_clergy_invitations",
    )

    status = models.CharField(
        _("statut"),
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    expires_at = models.DateTimeField(_("expire le"))

    class Meta:
        verbose_name = _("invitation clergé")
        verbose_name_plural = _("invitations clergé")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Invitation({self.email} — {self.pastoral_role})"

    @property
    def is_valid(self) -> bool:
        return self.status == self.Status.PENDING and timezone.now() < self.expires_at

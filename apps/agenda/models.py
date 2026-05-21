from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel


class Event(BaseModel):
    class EventType(models.TextChoices):
        MASS = "mass", _("Messe")
        CONFERENCE = "conference", _("Conférence")
        RETREAT = "retreat", _("Retraite")
        ORDINATION = "ordination", _("Ordination")
        OTHER = "other", _("Autre")

    class ScopeType(models.TextChoices):
        GLOBAL = "global", _("Mondial")
        PROVINCE = "province", _("Province")
        DIOCESE = "diocese", _("Diocèse")
        PARISH = "parish", _("Paroisse")

    title = models.CharField(_("titre"), max_length=200)
    description = models.TextField(_("description"), blank=True)
    event_type = models.CharField(
        _("type"),
        max_length=20,
        choices=EventType.choices,
        default=EventType.OTHER,
        db_index=True,
    )
    start_at = models.DateTimeField(_("début"), db_index=True)
    end_at = models.DateTimeField(_("fin"))
    location = models.CharField(_("lieu"), max_length=300, blank=True)
    organizer = models.ForeignKey(
        "users.BaseUser",
        on_delete=models.SET_NULL,
        null=True,
        related_name="organized_events",
    )
    scope_type = models.CharField(
        _("portée"),
        max_length=20,
        choices=ScopeType.choices,
        default=ScopeType.GLOBAL,
        db_index=True,
    )
    scope_id = models.IntegerField(_("ID territoire"), null=True, blank=True)
    max_participants = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["start_at"]
        verbose_name = _("Événement")
        verbose_name_plural = _("Événements")
        indexes = [
            models.Index(fields=["start_at", "scope_type"], name="event_start_scope_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.start_at.date()})"


class EventRegistration(BaseModel):
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="registrations",
    )
    user = models.ForeignKey(
        "users.BaseUser",
        on_delete=models.CASCADE,
        related_name="event_registrations",
    )
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [["event", "user"]]
        verbose_name = _("Inscription événement")
        verbose_name_plural = _("Inscriptions événements")

    def __str__(self) -> str:
        return f"Registration({self.user_id} → event {self.event_id})"

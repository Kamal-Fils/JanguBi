import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel
from apps.users.models import BaseUser


class PastoralReflection(BaseModel):
    """Réflexion pastorale du jour, publiée par un membre du clergé à une portée
    territoriale (paroisse / diocèse / global), visible des fidèles de cette portée.

    Une seule réflexion par auteur et par date (``unique_together``). La portée
    réutilise le vocabulaire partagé (``scope_type`` + FK ``scope_*``) consommé par
    ``apps.users.scoping.get_scoped_queryset``.
    """

    class ScopeType(models.TextChoices):
        GLOBAL = "global", _("Global (toute l'Église du Sénégal)")
        DIOCESE = "diocese", _("Diocèse")
        PARISH = "parish", _("Paroisse")
        CHURCH = "church", _("Église")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    author = models.ForeignKey(
        BaseUser,
        on_delete=models.CASCADE,
        related_name="pastoral_reflections",
        verbose_name=_("Auteur"),
    )
    reflection_date = models.DateField(db_index=True, verbose_name=_("Date de la réflexion"))
    title = models.CharField(max_length=200, blank=True, default="", verbose_name=_("Titre"))
    content = models.TextField(verbose_name=_("Contenu"))

    scope_type = models.CharField(
        max_length=20,
        choices=ScopeType.choices,
        default=ScopeType.PARISH,
        db_index=True,
        verbose_name=_("Portée"),
    )
    scope_parish = models.ForeignKey(
        "org.Parish", null=True, blank=True, on_delete=models.CASCADE,
        related_name="pastoral_reflections", verbose_name=_("Paroisse"),
    )
    scope_diocese = models.ForeignKey(
        "org.Diocese", null=True, blank=True, on_delete=models.CASCADE,
        related_name="pastoral_reflections", verbose_name=_("Diocèse"),
    )
    scope_church = models.ForeignKey(
        "org.Church", null=True, blank=True, on_delete=models.CASCADE,
        related_name="pastoral_reflections", verbose_name=_("Église"),
    )

    class Meta:
        verbose_name = _("Réflexion pastorale")
        verbose_name_plural = _("Réflexions pastorales")
        ordering = ["-reflection_date", "-created_at"]
        # Une réflexion par auteur et par jour.
        unique_together = ("author", "reflection_date")
        indexes = [
            models.Index(fields=["reflection_date", "scope_type"], name="idx_reflection_date_scope"),
        ]

    def __str__(self) -> str:
        return f"Réflexion {self.reflection_date} — {self.scope_type} ({self.author_id})"

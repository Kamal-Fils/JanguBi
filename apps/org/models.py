from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel
from apps.org.enums import ChurchType


class Province(BaseModel):
    name = models.CharField(_("nom"), max_length=200)
    code = models.CharField(_("code"), max_length=10, unique=True)
    country = models.CharField(_("pays"), max_length=100, default="Senegal")

    class Meta:
        verbose_name = _("province")
        verbose_name_plural = _("provinces")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Diocese(BaseModel):
    name = models.CharField(_("nom"), max_length=200)
    code = models.CharField(_("code"), max_length=10, unique=True)
    province = models.ForeignKey(
        Province,
        verbose_name=_("province"),
        on_delete=models.PROTECT,
        related_name="dioceses",
    )

    class Meta:
        verbose_name = _("diocèse")
        verbose_name_plural = _("diocèses")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Parish(BaseModel):
    name = models.CharField(_("nom"), max_length=200)
    diocese = models.ForeignKey(
        Diocese,
        verbose_name=_("diocèse"),
        on_delete=models.PROTECT,
        related_name="parishes",
    )
    deanery = models.ForeignKey(
        "org.Deanery",
        verbose_name=_("doyenné"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="parishes",
    )
    address = models.TextField(_("adresse"), blank=True, default="")
    city = models.CharField(_("ville"), max_length=100, blank=True, default="")

    class Meta:
        verbose_name = _("paroisse")
        verbose_name_plural = _("paroisses")
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.city})" if self.city else self.name


class ReligiousOrder(BaseModel):
    name = models.CharField(_("nom"), max_length=200)
    abbreviation = models.CharField(_("abréviation"), max_length=20)

    class Meta:
        verbose_name = _("ordre religieux")
        verbose_name_plural = _("ordres religieux")
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.abbreviation})"


class ReligiousCommunity(BaseModel):
    name = models.CharField(_("nom"), max_length=200)
    order = models.ForeignKey(
        ReligiousOrder,
        verbose_name=_("ordre"),
        on_delete=models.PROTECT,
        related_name="communities",
    )
    diocese = models.ForeignKey(
        Diocese,
        verbose_name=_("diocèse"),
        on_delete=models.PROTECT,
        related_name="communities",
    )
    parish = models.ForeignKey(
        Parish,
        verbose_name=_("paroisse"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="communities",
    )

    class Meta:
        verbose_name = _("communauté religieuse")
        verbose_name_plural = _("communautés religieuses")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Deanery(BaseModel):
    """
    Doyenné (vicariat forain) — regroupement de paroisses voisines au sein d'un
    diocèse, dirigé par un doyen (canon 524). Optionnel : une paroisse peut ne pas
    avoir de doyenné. Sert à modéliser le supérieur immédiat du curé.
    """

    name = models.CharField(_("nom"), max_length=200)
    diocese = models.ForeignKey(
        Diocese,
        verbose_name=_("diocèse"),
        on_delete=models.PROTECT,
        related_name="deaneries",
    )
    dean = models.ForeignKey(
        "users.BaseUser",
        verbose_name=_("doyen"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="led_deaneries",
    )

    class Meta:
        verbose_name = _("doyenné")
        verbose_name_plural = _("doyennés")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Church(BaseModel):
    """
    Église (bâtiment / lieu de culte) appartenant à une paroisse.

    Une paroisse possède exactement une église principale (``is_main=True``,
    l'église paroissiale) et zéro ou plusieurs églises secondaires
    (succursales, chapelles, stations). La règle « ≥ 1 église par paroisse,
    dont 1 principale » est garantie par le service ``parish_create`` (création
    automatique de l'église paroissiale) ; la base garantit « au plus une
    principale » via une contrainte d'unicité partielle.
    """

    parish = models.ForeignKey(
        Parish,
        verbose_name=_("paroisse"),
        on_delete=models.PROTECT,
        related_name="churches",
    )
    name = models.CharField(_("nom"), max_length=200)
    church_type = models.CharField(
        _("type d'église"),
        max_length=20,
        choices=ChurchType.choices,
        default=ChurchType.PAROISSIALE,
        db_index=True,
    )
    is_main = models.BooleanField(
        _("église principale"),
        default=False,
        db_index=True,
        help_text=_("L'église paroissiale principale. Une seule par paroisse."),
    )
    address = models.TextField(_("adresse"), blank=True, default="")
    city = models.CharField(_("ville"), max_length=100, blank=True, default="")
    latitude = models.DecimalField(
        _("latitude"), max_digits=9, decimal_places=6, null=True, blank=True
    )
    longitude = models.DecimalField(
        _("longitude"), max_digits=9, decimal_places=6, null=True, blank=True
    )
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("église")
        verbose_name_plural = _("églises")
        ordering = ["parish__name", "-is_main", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["parish"],
                condition=models.Q(is_main=True),
                name="unique_main_church_per_parish",
            ),
        ]

    def __str__(self) -> str:
        suffix = " ★" if self.is_main else ""
        return f"{self.name}{suffix}"

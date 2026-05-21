from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel


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

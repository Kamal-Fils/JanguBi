from django.db import models
from django.utils.translation import gettext_lazy as _


class ChurchType(models.TextChoices):
    """
    Typologie canonique des lieux de culte d'une paroisse.

    - PAROISSIALE : l'église paroissiale principale (canon 515). Une seule par paroisse.
    - SUCCURSALE  : église secondaire dépendante de la paroisse.
    - CHAPELLE    : lieu de culte sans statut paroissial (canons 1223-1235).
    - STATION     : lieu reculé desservi ponctuellement, sans clergé résident
                    (fréquent en zone rurale sénégalaise).
    """

    PAROISSIALE = ("paroissiale", _("Église paroissiale"))
    SUCCURSALE  = ("succursale",  _("Succursale"))
    CHAPELLE    = ("chapelle",    _("Chapelle"))
    STATION     = ("station",     _("Station / Mission"))

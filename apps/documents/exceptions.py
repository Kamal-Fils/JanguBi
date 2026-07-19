"""Exceptions domaine de l'app documents.

Les sélecteurs et services ne lèvent JAMAIS d'exception HTTP (``Http404``,
``PermissionDenied``…) : un appelant non-HTTP — tâche Celery, commande de
management, test — recevrait une exception qui n'a aucun sens dans son contexte.
La traduction en code HTTP appartient à la couche `apis.py`.
"""

from apps.core.exceptions import ApplicationError


class DocumentRequestNotFoundError(ApplicationError):
    """Demande inexistante **ou** hors du périmètre d'autorité de l'appelant.

    Les deux cas sont volontairement indiscernables : répondre 403 sur une
    demande d'une autre paroisse révélerait son existence (fuite PII
    inter-paroisse). `apis.py` mappe cette exception en **404**.
    """

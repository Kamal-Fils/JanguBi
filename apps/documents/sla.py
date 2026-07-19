"""Délais de traitement des demandes de documents (SLA).

Source unique des règles de délai, alignée sur ce que la tâche Celery
`document_requests_auto_escalate` relance réellement
(`services.document_request_run_escalation`) :

- l'ancienneté se mesure sur ``updated_at`` — le temps écoulé depuis la
  DERNIÈRE action, pas depuis la création ;
- le seuil dépend du statut (relance fidèle, rappel de dépôt, escalade) ;
- les statuts terminaux n'ont pas de délai.

Le frontend consommait auparavant sa propre copie de ces règles (âge calculé
sur ``created_at``, seuil unique de 7 jours) : les deux définitions avaient
déjà divergé. Les valeurs exposées par l'API viennent désormais d'ici.
"""

from django.conf import settings
from django.utils import timezone

from apps.documents.models import DocumentRequest

# Statuts sans délai : la demande est close, plus rien n'est attendu.
TERMINAL_STATUSES = frozenset(
    {
        DocumentRequest.Status.DOCUMENT_DEPOSITED,
        DocumentRequest.Status.REJECTED,
    }
)


def sla_threshold_days(status: str) -> int | None:
    """Seuil applicable au statut courant, ou ``None`` si terminal.

    Les défauts reproduisent ceux de la tâche Celery afin qu'un réglage absent
    donne le même comportement des deux côtés.
    """
    if status in TERMINAL_STATUSES:
        return None
    if status == DocumentRequest.Status.VALIDATED:
        return getattr(settings, "DOCS_DEPOSIT_REMINDER_DAYS", 3)
    if status == DocumentRequest.Status.INFO_REQUESTED:
        return getattr(settings, "DOCS_REQUESTER_REMINDER_DAYS", 5)
    # submitted / under_verification
    return getattr(settings, "DOCS_ESCALATE_DAYS", 7)


def sla_days(request_obj: DocumentRequest, *, now=None) -> int | None:
    """Jours entiers écoulés depuis la dernière action, ``None`` si terminal."""
    if request_obj.status in TERMINAL_STATUSES:
        return None
    if not request_obj.updated_at:
        return None
    reference = now or timezone.now()
    return max(0, (reference - request_obj.updated_at).days)


def is_escalated(request_obj: DocumentRequest, *, now=None) -> bool:
    """La demande a-t-elle dépassé le délai que le backend surveille ?"""
    threshold = sla_threshold_days(request_obj.status)
    if threshold is None:
        return False
    elapsed = sla_days(request_obj, now=now)
    if elapsed is None:
        return False
    return elapsed >= threshold

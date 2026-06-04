"""Opérations réutilisables pour les migrations data de l'app agenda.

Signatures STABLES (injection des modèles) pour être appelées depuis une
``RunPython`` ET testées directement.
"""

from __future__ import annotations


def resolve_scope_fk(*, value, Model):
    """Résout un id placeholder vers un pk valide du ``Model`` cible.

    ``(None, False)`` si value None ; ``(value, False)`` si existant ;
    ``(None, True)`` si introuvable (à flaguer, AUCUNE exception).
    """
    if value is None:
        return None, False
    if Model.objects.filter(pk=value).exists():
        return value, False
    return None, True


def backfill_event_scope_fks(*, Event, Parish, Diocese):
    """Convertit ``legacy_scope_id`` (ambigu, désambiguïsé par ``scope_type``) en
    FK réelles ``scope_parish`` / ``scope_diocese``.

    DÉFENSIF (jamais d'exception, jamais de ligne perdue) :
    - parish/diocese : id introuvable → flagué et laissé NULL ;
    - province : niveau non supporté dans le nouveau modèle → défaut GLOBAL + flagué ;
    - global : inchangé.

    Retourne ``(resolved_count, flagged)`` ; ``flagged`` = liste de dicts
    ``{"event_id", "scope_type", "value", "action"}``.
    """
    resolved = 0
    flagged: list[dict] = []

    for event in Event.objects.iterator():
        scope_type = event.scope_type
        value = event.legacy_scope_id

        if scope_type == "parish":
            pk, flag = resolve_scope_fk(value=value, Model=Parish)
            if pk is not None:
                event.scope_parish_id = pk
                resolved += 1
                event.save(update_fields=["scope_parish_id"])
            elif flag:
                flagged.append(
                    {
                        "event_id": event.id,
                        "scope_type": "parish",
                        "value": value,
                        "action": "introuvable → NULL",
                    }
                )
        elif scope_type == "diocese":
            pk, flag = resolve_scope_fk(value=value, Model=Diocese)
            if pk is not None:
                event.scope_diocese_id = pk
                resolved += 1
                event.save(update_fields=["scope_diocese_id"])
            elif flag:
                flagged.append(
                    {
                        "event_id": event.id,
                        "scope_type": "diocese",
                        "value": value,
                        "action": "introuvable → NULL",
                    }
                )
        elif scope_type == "province":
            # Niveau province absent du nouveau modèle → défaut défendable GLOBAL + flag.
            event.scope_type = "global"
            event.save(update_fields=["scope_type"])
            flagged.append(
                {
                    "event_id": event.id,
                    "scope_type": "province",
                    "value": value,
                    "action": "→ global (province non supportée)",
                }
            )
        # global → rien

    return resolved, flagged

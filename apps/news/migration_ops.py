"""Opérations réutilisables pour les migrations data de l'app news.

Signatures STABLES (injection des modèles) pour être appelées depuis une
``RunPython`` ET testées directement.
"""

from __future__ import annotations


def resolve_scope_fk(*, value, Model):
    """Résout une valeur d'id placeholder vers un pk valide du ``Model`` cible.

    Retourne ``(pk, flagged)`` :
    - ``value`` None → ``(None, False)`` (rien à résoudre, pas un échec) ;
    - id existant dans ``Model`` → ``(value, False)`` ;
    - id introuvable → ``(None, True)`` (à flaguer ; AUCUNE exception).
    """
    if value is None:
        return None, False
    if Model.objects.filter(pk=value).exists():
        return value, False
    return None, True


def backfill_article_scope_fks(*, Article, Parish, Diocese):
    """Convertit les ids placeholder (``legacy_scope_parish_id`` /
    ``legacy_scope_diocese_id``) en FK réelles (``scope_parish`` / ``scope_diocese``).

    DÉFENSIF : un id introuvable est flaguÉ et laissé NULL — la ligne (article)
    n'est JAMAIS perdue, aucune exception. Idempotent.

    Retourne ``(resolved_count, flagged)`` où ``flagged`` est une liste de dicts
    ``{"article_id", "field", "value"}`` à reprendre manuellement.
    """
    resolved = 0
    flagged: list[dict] = []

    qs = Article.objects.exclude(
        legacy_scope_parish_id__isnull=True, legacy_scope_diocese_id__isnull=True
    )
    for article in qs.iterator():
        changed: list[str] = []

        pk, flag = resolve_scope_fk(value=article.legacy_scope_parish_id, Model=Parish)
        if pk is not None:
            article.scope_parish_id = pk
            resolved += 1
            changed.append("scope_parish_id")
        elif flag:
            flagged.append(
                {
                    "article_id": str(article.id),
                    "field": "scope_parish_id",
                    "value": article.legacy_scope_parish_id,
                }
            )

        pk, flag = resolve_scope_fk(value=article.legacy_scope_diocese_id, Model=Diocese)
        if pk is not None:
            article.scope_diocese_id = pk
            resolved += 1
            changed.append("scope_diocese_id")
        elif flag:
            flagged.append(
                {
                    "article_id": str(article.id),
                    "field": "scope_diocese_id",
                    "value": article.legacy_scope_diocese_id,
                }
            )

        if changed:
            article.save(update_fields=changed)

    return resolved, flagged

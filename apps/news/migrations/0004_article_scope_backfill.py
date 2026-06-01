"""Chantier 3a — conversion scope_*_id en FK. Étape 2/3 (data).

Résout legacy_scope_parish_id / legacy_scope_diocese_id vers les FK réelles.
DÉFENSIF : ids introuvables flagués et laissés NULL (jamais de ligne perdue,
jamais d'exception) ; liste imprimée pour reprise manuelle.
"""

from django.db import migrations


def forward(apps, schema_editor):
    from apps.news.migration_ops import backfill_article_scope_fks

    Article = apps.get_model("news", "Article")
    Parish = apps.get_model("org", "Parish")
    Diocese = apps.get_model("org", "Diocese")

    resolved, flagged = backfill_article_scope_fks(
        Article=Article, Parish=Parish, Diocese=Diocese
    )

    print(f"\n[article_scope_backfill] {resolved} référence(s) scope résolue(s) en FK.")
    if flagged:
        print(
            f"[article_scope_backfill] ⚠ {len(flagged)} référence(s) scope INTROUVABLE(s) "
            "— laissées NULL, à reprendre manuellement :"
        )
        for entry in flagged:
            print(
                f"  - article={entry['article_id']} {entry['field']}={entry['value']} (introuvable)"
            )
    else:
        print("[article_scope_backfill] Aucune référence scope introuvable. ✔")


def reverse(apps, schema_editor):
    """Restaure les entiers legacy depuis les FK (rollback data-preserving)."""
    Article = apps.get_model("news", "Article")
    for article in Article.objects.iterator():
        article.legacy_scope_parish_id = article.scope_parish_id
        article.legacy_scope_diocese_id = article.scope_diocese_id
        article.save(update_fields=["legacy_scope_parish_id", "legacy_scope_diocese_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("news", "0003_article_scope_fk_pre"),
    ]

    operations = [
        migrations.RunPython(forward, reverse),
    ]

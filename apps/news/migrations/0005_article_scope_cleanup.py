"""Chantier 3a — conversion scope_*_id en FK. Étape 3/3 (schéma-post).

Supprime les colonnes legacy_* (valeurs déjà transférées vers les FK à l'étape 2)
et reconstruit la contrainte d'unicité + les index sur les nouvelles FK
(mêmes noms, mêmes colonnes scope_parish_id / scope_diocese_id), plus un index
sur scope_church.

Le reverse (auto) re-crée les colonnes legacy_* (vides) puis l'étape 2 reverse
les repeuple depuis les FK → rollback complet data-preserving.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("news", "0004_article_scope_backfill"),
    ]

    operations = [
        migrations.RemoveField(model_name="article", name="legacy_scope_parish_id"),
        migrations.RemoveField(model_name="article", name="legacy_scope_diocese_id"),
        migrations.AddIndex(
            model_name="article",
            index=models.Index(
                fields=["scope_type", "scope_parish", "status"], name="article_parish_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="article",
            index=models.Index(
                fields=["scope_type", "scope_diocese", "status"], name="article_diocese_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="article",
            index=models.Index(
                fields=["scope_type", "scope_church", "status"], name="article_church_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="article",
            constraint=models.UniqueConstraint(
                fields=("slug", "scope_type", "scope_parish"), name="unique_article_slug_parish"
            ),
        ),
    ]

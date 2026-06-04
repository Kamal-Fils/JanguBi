"""Chantier 3a — conversion scope_*_id (IntegerField placeholders) en FK réelles.

Étape 1/3 (schéma-pré, data-preserving) : on retire les contraintes/index qui
référencent les colonnes entières, on RENOMME ces colonnes en ``legacy_*`` (les
valeurs sont conservées), puis on ajoute les vraies FK (qui récupèrent les noms
de colonnes libérés). La résolution legacy → FK se fait à l'étape 2 (data).
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("news", "0002_add_content_type_to_article"),
        ("org", "0003_backfill_main_church"),
    ]

    operations = [
        # Lever les contraintes/index composites assis sur les colonnes entières.
        migrations.RemoveConstraint(model_name="article", name="unique_article_slug_parish"),
        migrations.RemoveIndex(model_name="article", name="article_parish_idx"),
        migrations.RemoveIndex(model_name="article", name="article_diocese_idx"),
        # Retirer le db_index implicite (index mono-colonne) AVANT le rename : son
        # nom dérive de la colonne scope_*_id et entrerait sinon en collision avec
        # l'index de la future FK qui réutilise ce nom de colonne.
        migrations.AlterField(
            model_name="article",
            name="scope_parish_id",
            field=models.IntegerField(
                null=True, blank=True, verbose_name="ID paroisse (placeholder)"
            ),
        ),
        migrations.AlterField(
            model_name="article",
            name="scope_diocese_id",
            field=models.IntegerField(
                null=True, blank=True, verbose_name="ID diocèse (placeholder)"
            ),
        ),
        # Préserver les valeurs : renommer les colonnes placeholder en legacy_*.
        migrations.RenameField(
            model_name="article", old_name="scope_parish_id", new_name="legacy_scope_parish_id"
        ),
        migrations.RenameField(
            model_name="article", old_name="scope_diocese_id", new_name="legacy_scope_diocese_id"
        ),
        # Vraies FK (colonnes scope_parish_id / scope_diocese_id / scope_church_id désormais libres).
        migrations.AddField(
            model_name="article",
            name="scope_diocese",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="scoped_articles",
                to="org.diocese",
                verbose_name="Diocèse de portée",
            ),
        ),
        migrations.AddField(
            model_name="article",
            name="scope_parish",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="scoped_articles",
                to="org.parish",
                verbose_name="Paroisse de portée",
            ),
        ),
        migrations.AddField(
            model_name="article",
            name="scope_church",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="scoped_articles",
                to="org.church",
                verbose_name="Église de portée",
            ),
        ),
        # Ajouter le choix CHURCH au scope_type.
        migrations.AlterField(
            model_name="article",
            name="scope_type",
            field=models.CharField(
                choices=[
                    ("global", "Global (toute l'Église du Sénégal)"),
                    ("diocese", "Diocèse"),
                    ("parish", "Paroisse"),
                    ("church", "Église"),
                ],
                db_index=True,
                default="global",
                max_length=20,
                verbose_name="Portée",
            ),
        ),
    ]

"""Chantier 3b — conversion scope_id (IntegerField ambigu) en FK réelles.

Étape 1/3 (schéma-pré, data-preserving) : on renomme scope_id en legacy_scope_id
(valeurs conservées), on ajoute les vraies FK + index, et on aligne scope_type sur
global/diocese/parish/church (province retirée — traitée à l'étape data).
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agenda", "0001_initial"),
        ("org", "0003_backfill_main_church"),
    ]

    operations = [
        migrations.RenameField(
            model_name="event", old_name="scope_id", new_name="legacy_scope_id"
        ),
        migrations.AddField(
            model_name="event",
            name="scope_diocese",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="scoped_events",
                to="org.diocese",
                verbose_name="diocèse de portée",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="scope_parish",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="scoped_events",
                to="org.parish",
                verbose_name="paroisse de portée",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="scope_church",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="scoped_events",
                to="org.church",
                verbose_name="église de portée",
            ),
        ),
        migrations.AlterField(
            model_name="event",
            name="scope_type",
            field=models.CharField(
                choices=[
                    ("global", "Mondial"),
                    ("diocese", "Diocèse"),
                    ("parish", "Paroisse"),
                    ("church", "Église"),
                ],
                db_index=True,
                default="global",
                max_length=20,
                verbose_name="portée",
            ),
        ),
        migrations.AddIndex(
            model_name="event",
            index=models.Index(fields=["scope_type", "scope_parish"], name="event_parish_idx"),
        ),
        migrations.AddIndex(
            model_name="event",
            index=models.Index(fields=["scope_type", "scope_diocese"], name="event_diocese_idx"),
        ),
        migrations.AddIndex(
            model_name="event",
            index=models.Index(fields=["scope_type", "scope_church"], name="event_church_idx"),
        ),
    ]

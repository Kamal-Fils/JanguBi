"""Chantier 3b — conversion scope_id en FK. Étape 3/3 (schéma-post).

Supprime legacy_scope_id (valeurs déjà transférées vers les FK). Le reverse (auto)
re-crée la colonne (vide) puis l'étape 2 reverse la repeuple depuis les FK.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("agenda", "0003_event_scope_backfill"),
    ]

    operations = [
        migrations.RemoveField(model_name="event", name="legacy_scope_id"),
    ]

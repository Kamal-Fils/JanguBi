import secrets
from datetime import date

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

import apps.mass_intentions.models


def _backfill_references(apps_registry, schema_editor):
    """Attribue une référence unique à chaque intention déjà en base.

    Indispensable AVANT de poser ``unique=True`` : un ``AddField`` avec valeur
    par défaut n'évalue le défaut qu'une seule fois et écrirait la même chaîne
    sur toutes les lignes existantes — la contrainte d'unicité échouerait
    aussitôt sur la deuxième. On boucle donc ligne à ligne.

    La génération est recopiée ici plutôt qu'importée de ``models.py`` : une
    migration doit rester reproductible même si le code applicatif évolue.
    """
    MassIntention = apps_registry.get_model("mass_intentions", "MassIntention")
    seen: set[str] = set()
    for intention in MassIntention.objects.filter(reference="").iterator():
        # La date de création d'origine est plus parlante que celle du déploiement.
        created = getattr(intention, "created_at", None)
        day = (created.date() if created else date.today()).strftime("%Y%m%d")
        while True:
            candidate = f"INT-{day}-{secrets.token_hex(4).upper()}"
            if candidate not in seen:
                break
        seen.add(candidate)
        intention.reference = candidate
        intention.save(update_fields=["reference"])


def _noop(apps_registry, schema_editor):
    """Retour arrière : la colonne entière est supprimée par l'opération miroir."""


class Migration(migrations.Migration):
    dependencies = [
        ("mass_intentions", "0001_initial"),
        ("files", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Colonne permissive : aucune contrainte, toutes les lignes à "".
        migrations.AddField(
            model_name="massintention",
            name="reference",
            field=models.CharField(default="", max_length=32),
        ),
        # 2. Backfill ligne à ligne (valeurs distinctes).
        migrations.RunPython(_backfill_references, _noop),
        # 3. Contrainte d'unicité + défaut applicatif définitifs.
        migrations.AlterField(
            model_name="massintention",
            name="reference",
            field=models.CharField(
                default=apps.mass_intentions.models.generate_intention_reference,
                help_text="Référence publique citée sur le reçu numérique.",
                max_length=32,
                unique=True,
            ),
        ),
        migrations.AddField(
            model_name="massintention",
            name="receipt_file",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="mass_intention_receipts",
                to="files.file",
            ),
        ),
        migrations.CreateModel(
            name="MassIntentionStatusLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("from_status", models.CharField(blank=True, default="", max_length=20)),
                ("to_status", models.CharField(max_length=20)),
                ("comment", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "changed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="mass_intention_status_changes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "intention",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="status_logs",
                        to="mass_intentions.massintention",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at"],
                "indexes": [
                    models.Index(
                        fields=["intention", "created_at"], name="massint_log_idx"
                    )
                ],
            },
        ),
    ]

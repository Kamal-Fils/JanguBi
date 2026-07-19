from django.db import migrations, models


class Migration(migrations.Migration):
    """« Autre » pour le type de document, avec précision libre.

    - `document_type_free` : ajout de colonne avec `default=''` et `NOT NULL` —
      sûr sur table peuplée, les lignes existantes reçoivent la chaîne vide.
    - `document_type` : `AlterField` pour enregistrer le nouveau choix `other`.
      Les choices ne sont pas contraints en base (pas de CHECK constraint) : cette
      opération ne réécrit pas la table, elle aligne seulement l'état des migrations.
    """

    dependencies = [
        ('documents', '0003_backfill_document_target_parish'),
    ]

    operations = [
        migrations.AddField(
            model_name='documentrequest',
            name='document_type_free',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AlterField(
            model_name='documentrequest',
            name='document_type',
            field=models.CharField(
                choices=[
                    ('baptism', 'Certificat de baptême'),
                    ('first_communion', 'Attestation de première communion'),
                    ('confirmation', 'Attestation de confirmation'),
                    ('religious_marriage', 'Attestation de mariage religieux'),
                    ('godparent', 'Attestation parrain / marraine'),
                    ('other', 'Autre document'),
                ],
                db_index=True,
                max_length=30,
            ),
        ),
    ]

from django.db import migrations


def create_main_churches(apps, schema_editor):
    """RG-ORG-04 : chaque paroisse existante reçoit son église paroissiale principale."""
    Parish = apps.get_model("org", "Parish")
    Church = apps.get_model("org", "Church")
    for parish in Parish.objects.all().iterator():
        if not Church.objects.filter(parish=parish, is_main=True).exists():
            Church.objects.create(
                parish=parish,
                name=parish.name,
                church_type="paroissiale",
                is_main=True,
                city=parish.city,
                address=parish.address,
            )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("org", "0002_deanery_parish_deanery_church"),
    ]

    operations = [
        migrations.RunPython(create_main_churches, noop),
    ]

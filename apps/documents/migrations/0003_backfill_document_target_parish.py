from django.db import migrations


def backfill_target_parish(apps, schema_editor):
    """Rattache les demandes existantes à la paroisse principale de leur demandeur."""
    DocumentRequest = apps.get_model("documents", "DocumentRequest")
    Profile = apps.get_model("users", "Profile")

    profile_parish = dict(
        Profile.objects.exclude(primary_parish__isnull=True).values_list(
            "user_id", "primary_parish_id"
        )
    )
    for req in DocumentRequest.objects.filter(target_parish__isnull=True).iterator():
        parish_id = profile_parish.get(req.requester_id)
        if parish_id:
            req.target_parish_id = parish_id
            req.save(update_fields=["target_parish"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0002_documentrequest_target_parish"),
        ("users", "0004_backfill_role_assignments"),
    ]

    operations = [
        migrations.RunPython(backfill_target_parish, noop),
    ]

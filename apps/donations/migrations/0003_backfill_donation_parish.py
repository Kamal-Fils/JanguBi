from django.db import migrations


def backfill_parish_fk(apps, schema_editor):
    """Renseigne les FK paroisse réelles depuis l'ancien couple scope_type/scope_id."""
    DonationCampaign = apps.get_model("donations", "DonationCampaign")
    Donation = apps.get_model("donations", "Donation")
    Parish = apps.get_model("org", "Parish")

    valid_parish_ids = set(Parish.objects.values_list("id", flat=True))

    for campaign in DonationCampaign.objects.filter(
        scope_type="parish", parish__isnull=True
    ).iterator():
        if campaign.scope_id in valid_parish_ids:
            campaign.parish_id = campaign.scope_id
            campaign.save(update_fields=["parish"])

    for donation in (
        Donation.objects.filter(parish__isnull=True, campaign__isnull=False)
        .select_related("campaign")
        .iterator()
    ):
        if donation.campaign and donation.campaign.parish_id:
            donation.parish_id = donation.campaign.parish_id
            donation.save(update_fields=["parish"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("donations", "0002_donation_parish_donationcampaign_church_and_more"),
        ("org", "0003_backfill_main_church"),
    ]

    operations = [
        migrations.RunPython(backfill_parish_fk, noop),
    ]

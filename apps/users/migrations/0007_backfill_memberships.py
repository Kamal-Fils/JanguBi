from django.db import migrations


def forward(apps, schema_editor):
    """Backfill : une appartenance principale par Profile.primary_parish existant,
    sur l'église principale de la paroisse. Défensif (cf. migration_ops)."""
    from apps.users.migration_ops import backfill_memberships

    Profile = apps.get_model("users", "Profile")
    Church = apps.get_model("org", "Church")
    Membership = apps.get_model("users", "Membership")

    created, flagged = backfill_memberships(
        Profile=Profile, Church=Church, Membership=Membership
    )

    print(f"\n[backfill_memberships] {created} appartenance(s) principale(s) créée(s).")
    if flagged:
        print(
            f"[backfill_memberships] ⚠ {len(flagged)} paroisse(s) SANS église principale "
            "(is_main) — utilisateurs sautés, à reprendre manuellement :"
        )
        for entry in flagged:
            print(
                f"  - user={entry['user_id']} parish={entry['parish_id']} "
                f"« {entry['parish_name']} »"
            )
    else:
        print("[backfill_memberships] Aucune paroisse sans église principale. ✔")


def reverse(apps, schema_editor):
    # No-op sûr : on ne supprime aucune appartenance (pas de perte de données).
    # Un vrai rollback passe par l'annulation de 0006 (drop de la table Membership).
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0006_membership"),
    ]

    operations = [
        migrations.RunPython(forward, reverse),
    ]

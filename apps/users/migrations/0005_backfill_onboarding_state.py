from django.db import migrations

# Valeurs en dur (UserOnboardingState) : une migration de données ne doit pas
# dépendre du code applicatif, qui peut évoluer après coup.
_PENDING_EMAIL = "pending_email"
_PENDING_PARISH = "pending_parish"
_COMPLETED = "completed"


def backfill_onboarding_state(apps, schema_editor):
    """Rétro-remplit onboarding_state à partir de l'état réel des comptes.

    - vérifié + paroisse principale  → completed
    - vérifié sans paroisse          → pending_parish
    - non vérifié                    → pending_email
    """
    BaseUser = apps.get_model("users", "BaseUser")
    Profile = apps.get_model("users", "Profile")

    users_with_parish = set(
        Profile.objects
        .filter(primary_parish__isnull=False)
        .values_list("user_id", flat=True)
    )

    BaseUser.objects.filter(is_verified=False).update(onboarding_state=_PENDING_EMAIL)

    verified = BaseUser.objects.filter(is_verified=True)
    verified.filter(id__in=users_with_parish).update(onboarding_state=_COMPLETED)
    verified.exclude(id__in=users_with_parish).update(onboarding_state=_PENDING_PARISH)


def noop_reverse(apps, schema_editor):
    """Pas de rollback de données : l'état dérive de is_verified/primary_parish."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0004_backfill_role_assignments"),
    ]

    operations = [
        migrations.RunPython(backfill_onboarding_state, noop_reverse),
    ]

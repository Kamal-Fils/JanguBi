from django.db import migrations


def _primary_parish_id(Profile, user):
    profile = Profile.objects.filter(user=user).first()
    return profile.primary_parish_id if profile else None


def backfill_role_assignments(apps, schema_editor):
    """Dérive une RoleAssignment scopée à partir du rôle plat de chaque utilisateur."""
    BaseUser = apps.get_model("users", "BaseUser")
    RoleAssignment = apps.get_model("users", "RoleAssignment")
    Profile = apps.get_model("users", "Profile")
    Church = apps.get_model("org", "Church")

    def has_active(user, **kwargs):
        return RoleAssignment.objects.filter(user=user, is_active=True, **kwargs).exists()

    for user in BaseUser.objects.all().iterator():
        role = user.role

        if role == "super_admin":
            if not has_active(user, role="super_admin", scope="global"):
                RoleAssignment.objects.create(user=user, role=role, scope="global", is_active=True)

        elif role == "province_admin":
            if user.province_id and not has_active(user, scope="province", province_id=user.province_id):
                RoleAssignment.objects.create(
                    user=user, role=role, scope="province", province_id=user.province_id, is_active=True
                )

        elif role == "diocese_admin":
            if user.diocese_id and not has_active(user, scope="diocese", diocese_id=user.diocese_id):
                RoleAssignment.objects.create(
                    user=user, role=role, scope="diocese", diocese_id=user.diocese_id, is_active=True
                )

        elif role == "parish_admin":
            parish_id = _primary_parish_id(Profile, user)
            if parish_id and not has_active(user, scope="parish", parish_id=parish_id):
                has_principal = RoleAssignment.objects.filter(
                    parish_id=parish_id, scope="parish", is_principal=True, is_active=True
                ).exists()
                RoleAssignment.objects.create(
                    user=user,
                    role=role,
                    scope="parish",
                    parish_id=parish_id,
                    is_principal=not has_principal,
                    is_active=True,
                )

        elif role == "church_admin":
            parish_id = _primary_parish_id(Profile, user)
            if parish_id:
                main = Church.objects.filter(parish_id=parish_id, is_main=True).first()
                if main and not has_active(user, scope="church", church_id=main.id):
                    RoleAssignment.objects.create(
                        user=user, role=role, scope="church", church_id=main.id, is_active=True
                    )
                elif not main and not has_active(user, scope="parish", parish_id=parish_id):
                    RoleAssignment.objects.create(
                        user=user, role=role, scope="parish", parish_id=parish_id, is_active=True
                    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0003_roleassignment"),
        ("org", "0003_backfill_main_church"),
    ]

    operations = [
        migrations.RunPython(backfill_role_assignments, noop),
    ]

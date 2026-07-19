"""Chaîne de validation des comptes clergé.

Ajoute ``BaseUser.clergy_validation_status`` (distingue une auto-déclaration en
attente d'un compte clergé déjà validé) et les deux événements d'audit associés.

Backfill : tout compte clergé PRÉEXISTANT ne peut venir que de la voie invitation
(l'auto-déclaration n'existait pas). Accepter une invitation valant validation
hiérarchique, ces comptes sont marqués ``approved`` — sinon ils resteraient
``not_applicable``, ce qui décrirait mal la réalité. Idempotent et réversible.
"""

from django.db import migrations, models

_CLERGY_ROLES = ["religieux", "diacre", "pretre", "eveque", "archeveque"]


def approve_existing_clergy(apps, schema_editor):
    BaseUser = apps.get_model("users", "BaseUser")
    BaseUser.objects.filter(
        pastoral_role__in=_CLERGY_ROLES,
        clergy_validation_status="not_applicable",
    ).update(clergy_validation_status="approved")


def reset_clergy_validation(apps, schema_editor):
    BaseUser = apps.get_model("users", "BaseUser")
    BaseUser.objects.filter(clergy_validation_status="approved").update(
        clergy_validation_status="not_applicable"
    )


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0008_remove_followed_parishes'),
    ]

    operations = [
        migrations.AddField(
            model_name='baseuser',
            name='clergy_validation_status',
            field=models.CharField(choices=[('not_applicable', 'Sans objet (laïc)'), ('pending', 'En attente de validation'), ('approved', 'Validé'), ('rejected', 'Refusé')], db_index=True, default='not_applicable', max_length=20, verbose_name='validation du compte clergé'),
        ),
        migrations.AlterField(
            model_name='securityauditlog',
            name='event',
            field=models.CharField(choices=[('REGISTER', 'Inscription'), ('EMAIL_VERIFIED', 'Email vérifié'), ('LOGIN', 'Connexion'), ('LOGOUT', 'Déconnexion'), ('PWD_RESET_REQUEST', 'Demande réinitialisation MDP'), ('PWD_RESET_CONFIRM', 'Réinitialisation MDP confirmée'), ('PWD_CHANGED', 'Mot de passe modifié'), ('EMAIL_CHANGE_REQUEST', 'Demande changement email'), ('EMAIL_CHANGE_CONFIRM', 'Changement email confirmé'), ('EMAIL_CHANGE_REVERTED', 'Changement email annulé'), ('ACCOUNT_ACTIVATED', 'Compte activé'), ('ACCOUNT_DEACTIVATED', 'Compte désactivé'), ('ACCOUNT_SOFT_DELETED', 'Compte supprimé (soft)'), ('ACCOUNT_HARD_DELETED', 'Compte supprimé (définitif)'), ('ADMIN_CREATED', 'Compte créé par admin'), ('PROFILE_UPDATED', 'Profil mis à jour'), ('CLERGY_APPROVED', 'Compte clergé validé'), ('CLERGY_REJECTED', 'Compte clergé refusé')], db_index=True, max_length=50, verbose_name='événement'),
        ),
        migrations.RunPython(approve_existing_clergy, reset_clergy_validation),
    ]

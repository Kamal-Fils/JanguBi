from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver


@receiver(post_save, sender="users.Profile")
def sync_territorial_hierarchy(sender, instance, **kwargs):
    """LEGACY (Chantier 1 : conservé). Quand primary_parish change via Profile.save()
    → auto-remplit diocese et province sur BaseUser. Chemin parallèle à Membership ;
    son retrait est réservé au Chantier 2."""
    from apps.users.models import BaseUser  # import local pour éviter les circulaires

    user = instance.user
    if instance.primary_parish_id:
        parish = instance.primary_parish
        diocese = parish.diocese
        province = diocese.province
        BaseUser.objects.filter(pk=user.pk).update(
            diocese_id=diocese.pk,
            province_id=province.pk,
        )
    else:
        BaseUser.objects.filter(pk=user.pk).update(
            diocese_id=None,
            province_id=None,
        )


@receiver(post_save, sender="users.Membership")
@receiver(post_delete, sender="users.Membership")
def sync_hierarchy_from_membership(sender, instance, **kwargs):
    """Recalcule la hiérarchie territoriale dérivée de l'appartenance PRINCIPALE.

    Source de vérité : l'église ``is_primary`` de l'utilisateur. Met à jour
    ``BaseUser.diocese`` / ``province`` ET, en MIROIR transitoire (Chantier 1),
    ``Profile.primary_parish`` — pour que les lecteurs historiques continuent de
    fonctionner pendant la transition.

    Écrit via ``.update()`` sur BaseUser ET Profile (jamais ``.save()``) → aucun
    signal en cascade, pas de boucle avec le signal legacy ci-dessus. Plus aucune
    appartenance principale (0 appartenance) → on remet diocese/province/primary_parish
    à NULL.
    """
    from apps.users.models import BaseUser, Membership, Profile

    user_id = instance.user_id
    primary = (
        Membership.objects.filter(user_id=user_id, is_primary=True)
        .select_related("church__parish__diocese__province")
        .first()
    )

    if primary is not None:
        parish = primary.church.parish
        diocese = parish.diocese
        province = diocese.province
        BaseUser.objects.filter(pk=user_id).update(
            diocese_id=diocese.pk,
            province_id=province.pk,
        )
        Profile.objects.filter(user_id=user_id).update(primary_parish_id=parish.pk)
    else:
        BaseUser.objects.filter(pk=user_id).update(diocese_id=None, province_id=None)
        Profile.objects.filter(user_id=user_id).update(primary_parish_id=None)

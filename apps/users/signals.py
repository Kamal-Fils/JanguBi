from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender="users.Profile")
def sync_territorial_hierarchy(sender, instance, **kwargs):
    """Quand primary_parish change → auto-remplit diocese et province sur BaseUser."""
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
        if not user.followed_parishes.exists():
            BaseUser.objects.filter(pk=user.pk).update(
                diocese_id=None,
                province_id=None,
            )

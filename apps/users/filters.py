import django_filters

from apps.users.models import BaseUser


class BaseUserFilter(django_filters.FilterSet):
    class Meta:
        model = BaseUser
        fields = {
            "id": ["exact"],
            "email": ["exact", "icontains"],
            "role": ["exact"],
            "is_active": ["exact"],
            "is_verified": ["exact"],
            "is_admin": ["exact"],
        }

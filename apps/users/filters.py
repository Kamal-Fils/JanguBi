import django_filters

from apps.users.models import BaseUser


class BaseUserFilter(django_filters.FilterSet):
    # Filtre explicite : liste le clergé par identité pastorale
    # (?pastoral_role=pretre|eveque|…), dimension orthogonale au rôle admin.
    pastoral_role = django_filters.CharFilter(
        field_name="pastoral_role", lookup_expr="exact"
    )

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

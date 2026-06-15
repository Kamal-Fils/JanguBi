from drf_spectacular.utils import OpenApiExample, extend_schema_serializer
from rest_framework import serializers


class OrgRefSerializer(serializers.Serializer):
    """Référence légère {id, name} vers une entité territoriale."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)


class MembershipMeSerializer(serializers.Serializer):
    """Appartenance exposée dans /me : église + paroisse + diocèse + flag principal."""

    id = serializers.IntegerField(read_only=True)
    church = OrgRefSerializer(read_only=True)
    parish = OrgRefSerializer(read_only=True)
    diocese = OrgRefSerializer(read_only=True)
    is_primary = serializers.BooleanField(read_only=True)


@extend_schema_serializer(
    component_name="MonProfil",
    examples=[
        OpenApiExample(
            "Exemple Fidèle",
            value={
                "id": 1,
                "email": "jean.dupont@example.com",
                "role": "fidele",
                "pastoral_role": None,
                "onboarding_state": "completed",
                "is_active": True,
                "is_verified": True,
                "is_admin": False,
                "is_staff": False,
                "diocese": {"id": 2, "name": "Diocèse de Thiès"},
                "province": {"id": 1, "name": "Province de Dakar"},
                "profile": {
                    "first_name": "Jean",
                    "last_name": "Dupont",
                    "title": "MR",
                    "phone": "+221770000000",
                    "primary_parish": {"id": 5, "name": "Paroisse Saint-Pierre"},
                    "avatar": None,
                },
            },
        ),
    ],
)
class MeOutputSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    email = serializers.EmailField(read_only=True)
    phone_number = serializers.CharField(read_only=True)
    role = serializers.CharField(read_only=True)
    pastoral_role = serializers.CharField(
        read_only=True, allow_null=True, help_text="Rôle pastoral (clergé) ou null."
    )
    onboarding_state = serializers.CharField(
        read_only=True, help_text="pending_email | pending_parish | completed."
    )
    is_active = serializers.BooleanField(read_only=True)
    is_verified = serializers.BooleanField(read_only=True)
    is_admin = serializers.BooleanField(read_only=True)
    is_staff = serializers.BooleanField(read_only=True)
    diocese = OrgRefSerializer(read_only=True, allow_null=True)
    province = OrgRefSerializer(read_only=True, allow_null=True)
    profile = serializers.DictField(
        help_text="Objet profil. `primary_parish` y est exposé en {id, name} | null."
    )
    # Multi-appartenance (Chantier 2). Singuliers diocese/province/primary_parish =
    # principaux (rétro-compat) ; pluriels = toutes les appartenances.
    memberships = MembershipMeSerializer(
        many=True, read_only=True, help_text="Toutes les appartenances (principale en tête)."
    )
    church_ids = serializers.ListField(
        child=serializers.IntegerField(), read_only=True, help_text="IDs des églises."
    )
    parish_ids = serializers.ListField(
        child=serializers.IntegerField(), read_only=True, help_text="IDs des paroisses (distincts)."
    )
    diocese_ids = serializers.ListField(
        child=serializers.IntegerField(), read_only=True, help_text="IDs des diocèses (distincts)."
    )


class MeUpdateInputSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=50, required=False)
    last_name = serializers.CharField(max_length=50, required=False)
    title = serializers.ChoiceField(choices=["MR", "MRS"], required=False)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    primary_parish = serializers.IntegerField(required=False, allow_null=True)
    avatar = serializers.ImageField(required=False, allow_null=True)

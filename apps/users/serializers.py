from rest_framework import serializers
from drf_spectacular.utils import extend_schema_serializer, OpenApiExample


@extend_schema_serializer(
    component_name="MonProfil",
    examples=[
        OpenApiExample(
            "Exemple Fidèle",
            value={
                "id": 1,
                "email": "jean.dupont@example.com",
                "role": "fidele",
                "is_active": True,
                "profile": {
                    "first_name": "Jean",
                    "last_name": "Dupont",
                    "title": "MR",
                    "phone": "+221770000000",
                    "primary_parish": None,
                }
            }
        ),
    ]
)
class MeOutputSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    email = serializers.EmailField(read_only=True)
    phone_number = serializers.CharField(read_only=True)
    role = serializers.CharField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    is_verified = serializers.BooleanField(read_only=True)
    is_admin = serializers.BooleanField(read_only=True)
    is_staff = serializers.BooleanField(read_only=True)
    profile = serializers.DictField(help_text="Objet profil de l'utilisateur.")


class MeUpdateInputSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=50, required=False)
    last_name = serializers.CharField(max_length=50, required=False)
    title = serializers.ChoiceField(choices=["MR", "MRS"], required=False)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    primary_parish = serializers.IntegerField(required=False, allow_null=True)
    avatar = serializers.ImageField(required=False, allow_null=True)

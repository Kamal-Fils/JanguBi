from rest_framework import serializers

from apps.org.enums import ChurchType
from apps.org.models import Church, Deanery, Diocese, Parish, Province


class ProvinceOutputSerializer(serializers.ModelSerializer):
    class Meta:
        model = Province
        fields = ["id", "name", "code", "country"]


class DioceseOutputSerializer(serializers.ModelSerializer):
    province_name = serializers.CharField(source="province.name", read_only=True)

    class Meta:
        model = Diocese
        fields = ["id", "name", "code", "province", "province_name"]


class ParishOutputSerializer(serializers.ModelSerializer):
    diocese_name = serializers.CharField(source="diocese.name", read_only=True)
    province_id = serializers.IntegerField(source="diocese.province_id", read_only=True)
    province_name = serializers.CharField(source="diocese.province.name", read_only=True)

    class Meta:
        model = Parish
        fields = ["id", "name", "city", "address", "diocese", "diocese_name", "province_id", "province_name"]


class ProvinceCreateInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    code = serializers.CharField(max_length=10)
    country = serializers.CharField(max_length=100, default="Senegal")


class DioceseCreateInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    code = serializers.CharField(max_length=10)
    province_id = serializers.IntegerField()


class ParishCreateInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    diocese_id = serializers.IntegerField()
    city = serializers.CharField(max_length=100, default="", allow_blank=True)
    address = serializers.CharField(default="", allow_blank=True)


class ParishUpdateInputSerializer(serializers.Serializer):
    # Mise à jour partielle : tous les champs optionnels (le service ne touche
    # que ceux fournis). Le diocèse n'est PAS modifiable ici (déplacement de
    # paroisse = opération distincte, hors périmètre CRUD de base).
    name = serializers.CharField(max_length=200, required=False)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)


class ChurchOutputSerializer(serializers.ModelSerializer):
    parish_name = serializers.CharField(source="parish.name", read_only=True)
    church_type_label = serializers.CharField(source="get_church_type_display", read_only=True)

    class Meta:
        model = Church
        fields = [
            "id", "name", "church_type", "church_type_label", "is_main",
            "city", "address", "latitude", "longitude", "is_active",
            "parish", "parish_name",
        ]


class ChurchCreateInputSerializer(serializers.Serializer):
    parish_id = serializers.IntegerField()
    name = serializers.CharField(max_length=200)
    church_type = serializers.ChoiceField(choices=ChurchType.choices, default=ChurchType.SUCCURSALE)
    is_main = serializers.BooleanField(default=False)
    city = serializers.CharField(max_length=100, default="", allow_blank=True)
    address = serializers.CharField(default="", allow_blank=True)


class DeaneryOutputSerializer(serializers.ModelSerializer):
    diocese_name = serializers.CharField(source="diocese.name", read_only=True)
    dean_email = serializers.SerializerMethodField()

    class Meta:
        model = Deanery
        fields = ["id", "name", "diocese", "diocese_name", "dean", "dean_email"]

    def get_dean_email(self, obj) -> str | None:
        return obj.dean.email if obj.dean_id else None


class DeaneryCreateInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    diocese_id = serializers.IntegerField()
    dean_id = serializers.UUIDField(required=False, allow_null=True)

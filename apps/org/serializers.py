from rest_framework import serializers

from apps.org.models import Diocese, Parish, Province


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

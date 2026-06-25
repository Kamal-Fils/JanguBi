from rest_framework import serializers

from .models import ParishTransferRequest


class TransferCreateInputSerializer(serializers.Serializer):
    destination_parish_id = serializers.IntegerField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class TransferRejectInputSerializer(serializers.Serializer):
    reason = serializers.CharField()


class TransferOutputSerializer(serializers.ModelSerializer):
    origin_parish_name = serializers.CharField(
        source="origin_parish.name", read_only=True, allow_null=True
    )
    destination_parish_name = serializers.CharField(
        source="destination_parish.name", read_only=True, allow_null=True
    )

    class Meta:
        model = ParishTransferRequest
        fields = [
            "id",
            "status",
            "reason",
            "rejection_reason",
            "origin_parish_name",
            "destination_parish_name",
            "created_at",
            "updated_at",
        ]

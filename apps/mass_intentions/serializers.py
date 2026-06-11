from rest_framework import serializers

from .models import MassIntention, MassIntentionType


class MassIntentionSubmitInputSerializer(serializers.Serializer):
    intention_type = serializers.ChoiceField(choices=MassIntentionType.choices)
    intention_text = serializers.CharField(min_length=10)
    parish_id = serializers.IntegerField(required=False, allow_null=True)


class MassIntentionProposeDateInputSerializer(serializers.Serializer):
    proposed_date = serializers.DateField()


class MassIntentionDeclineInputSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class MassIntentionOutputSerializer(serializers.ModelSerializer):
    requestor_email = serializers.EmailField(source="requestor.email", read_only=True)
    pretre_email = serializers.EmailField(
        source="pretre.email", read_only=True, allow_null=True
    )
    parish_name = serializers.CharField(
        source="parish.name", read_only=True, allow_null=True
    )

    class Meta:
        model = MassIntention
        fields = [
            "id",
            "intention_type",
            "intention_text",
            "status",
            "requestor_email",
            "pretre_email",
            "parish_name",
            "proposed_date",
            "celebration_date",
            "notes",
            "created_at",
            "updated_at",
        ]

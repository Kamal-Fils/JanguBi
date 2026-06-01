from rest_framework import serializers

from .models import Donation, DonationCampaign, DonationType, PaymentProvider


class CampaignCreateInputSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    donation_type = serializers.ChoiceField(choices=DonationType.choices)
    target_amount = serializers.DecimalField(
        max_digits=12, decimal_places=0, required=False, allow_null=True
    )
    scope_type = serializers.CharField(default="global")
    scope_id = serializers.IntegerField(required=False, allow_null=True)
    parish_id = serializers.IntegerField(required=False, allow_null=True)
    church_id = serializers.IntegerField(required=False, allow_null=True)


class CampaignOutputSerializer(serializers.ModelSerializer):
    created_by_email = serializers.EmailField(
        source="created_by.email", read_only=True, allow_null=True
    )
    total_donations = serializers.SerializerMethodField()

    def get_total_donations(self, obj) -> int:
        return obj.donations.filter(status="confirmed").count()

    class Meta:
        model = DonationCampaign
        fields = [
            "id",
            "title",
            "description",
            "donation_type",
            "target_amount",
            "currency",
            "scope_type",
            "scope_id",
            "parish",
            "church",
            "is_active",
            "starts_at",
            "ends_at",
            "created_by_email",
            "total_donations",
        ]


class DonationMakeInputSerializer(serializers.Serializer):
    campaign_id = serializers.IntegerField(required=False, allow_null=True)
    amount = serializers.DecimalField(max_digits=10, decimal_places=0, min_value=1)
    payment_provider = serializers.ChoiceField(choices=PaymentProvider.choices)
    is_anonymous = serializers.BooleanField(default=False)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    # Étiquetage (B6a) — défaut = église/paroisse principale du donateur côté service.
    church_id = serializers.IntegerField(required=False, allow_null=True)
    parish_id = serializers.IntegerField(required=False, allow_null=True)
    # Don anonyme (RG-PAY-01/02).
    anonymous_donor_name = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=120
    )
    anonymous_donor_phone = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=30
    )


class DonationConfirmInputSerializer(serializers.Serializer):
    payment_reference = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=200
    )


class DonationOutputSerializer(serializers.ModelSerializer):
    campaign_title = serializers.CharField(
        source="campaign.title", read_only=True, allow_null=True
    )

    class Meta:
        model = Donation
        fields = [
            "id",
            "campaign_title",
            "amount",
            "currency",
            "payment_provider",
            "status",
            "is_anonymous",
            "note",
            "created_at",
        ]

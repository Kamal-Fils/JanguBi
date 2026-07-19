from rest_framework import serializers

from .models import MassIntention, MassIntentionType


class MassIntentionSubmitInputSerializer(serializers.Serializer):
    intention_type = serializers.ChoiceField(choices=MassIntentionType.choices)
    intention_text = serializers.CharField(min_length=10)
    parish_id = serializers.IntegerField(required=False, allow_null=True)


class MassIntentionProposeDateInputSerializer(serializers.Serializer):
    proposed_date = serializers.DateField()


class MassIntentionCelebrateInputSerializer(serializers.Serializer):
    """Corps optionnel : le prêtre peut acter la date réelle de célébration.

    Tout est facultatif — un ``POST {}`` reste valide et laisse le service
    retomber sur la date confirmée/proposée, puis sur aujourd'hui.
    """

    celebration_date = serializers.DateField(required=False, allow_null=True)


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
    receipt_url = serializers.SerializerMethodField()

    class Meta:
        model = MassIntention
        fields = [
            "id",
            "reference",
            "intention_type",
            "intention_text",
            "status",
            "requestor_email",
            "pretre_email",
            "parish_name",
            "proposed_date",
            "celebration_date",
            "receipt_url",
            "notes",
            "created_at",
            "updated_at",
        ]

    def get_receipt_url(self, obj) -> str | None:
        """URL du reçu, ou ``None`` tant qu'il n'y en a pas.

        Un fichier dont l'upload n'est pas terminé (``is_valid`` faux) n'est
        jamais exposé : mieux vaut pas de lien qu'un lien mort.
        """
        if not obj.receipt_file_id:
            return None
        receipt = obj.receipt_file
        if not receipt.file or not receipt.is_valid:
            return None
        return receipt.url


class MassIntentionReceiptOutputSerializer(serializers.Serializer):
    """Charge utile de l'endpoint de reçu — volontairement minimale."""

    reference = serializers.CharField()
    receipt_url = serializers.CharField(allow_null=True)
    celebration_date = serializers.DateField(allow_null=True)


class MassIntentionStatusLogOutputSerializer(serializers.Serializer):
    from_status = serializers.CharField()
    to_status = serializers.CharField()
    comment = serializers.CharField()
    created_at = serializers.DateTimeField()
    changed_by_email = serializers.EmailField(
        source="changed_by.email", allow_null=True, required=False
    )

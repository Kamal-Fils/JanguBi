from rest_framework import serializers

from apps.documents import sla
from apps.documents.models import (
    DocumentRequest,
    DocumentRequestAttachment,
    DocumentRequestStatusLog,
    InternalNote,
)


def _user_display_name(user) -> str:
    profile = getattr(user, "profile", None)
    if profile:
        name = f"{profile.first_name} {profile.last_name}".strip()
        if name:
            return name
    return user.email


# ---------------------------------------------------------------------------
# Input serializers
# ---------------------------------------------------------------------------


class DocumentRequestCreateInputSerializer(serializers.Serializer):
    document_type = serializers.ChoiceField(choices=DocumentRequest.DocumentType.choices)
    # Précision libre exigée quand le choix est « Autre » — l'obligation est portée
    # par le service (apps.documents.services), qui est aussi la voie d'appel des
    # tests et de toute future intégration.
    document_type_free = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
    reason = serializers.ChoiceField(choices=DocumentRequest.RequestReason.choices)
    reason_free = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")

    # Identité
    requester_last_name = serializers.CharField(max_length=100)
    requester_first_names = serializers.CharField(max_length=200)
    date_of_birth = serializers.DateField()
    place_of_birth = serializers.CharField(max_length=200)

    # Contact
    contact_phone = serializers.CharField(max_length=30)
    contact_email = serializers.EmailField()

    # Recherche
    registered_last_name = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    registered_first_names = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    father_last_name = serializers.CharField(max_length=100)
    mother_last_name = serializers.CharField(max_length=100)
    # B5c — Paroisse du registre : FK OBLIGATOIRE (le front l'émet via le picker).
    # parish_name/diocese ne sont plus acceptés en entrée : le nom et le diocèse sont
    # dérivés de target_parish (C4). Les extras éventuels du front sont ignorés par DRF.
    parish_id = serializers.IntegerField()
    sacrament_approximate_date = serializers.CharField(max_length=20)
    sacrament_location = serializers.CharField(max_length=200)
    additional_info = serializers.CharField(required=False, allow_blank=True, default="")

    # Champs dynamiques + consentement
    document_details = serializers.DictField(
        child=serializers.CharField(allow_blank=True), required=False, default=dict
    )
    consent_given = serializers.BooleanField()

    # Pièce jointe initiale (optionnelle)
    attachment_file_id = serializers.IntegerField(required=False, allow_null=True)

    def validate_consent_given(self, value):
        if not value:
            raise serializers.ValidationError(
                "Le consentement est obligatoire pour soumettre une demande."
            )
        return value


class DocumentRequestSupplementInputSerializer(serializers.Serializer):
    additional_info = serializers.CharField(required=False, allow_blank=True)
    document_details = serializers.DictField(
        child=serializers.CharField(allow_blank=True), required=False
    )


class StatusActionWithCommentInputSerializer(serializers.Serializer):
    comment = serializers.CharField(allow_blank=True, default="")


class RejectInputSerializer(serializers.Serializer):
    reason = serializers.CharField()


class DepositDocumentInputSerializer(serializers.Serializer):
    file_id = serializers.IntegerField()
    label = serializers.CharField(  # type: ignore[assignment]  # drf-stubs : collision avec l'attribut Field.label
        max_length=255, required=False, allow_blank=True, default="Document officiel"
    )


class InternalNoteCreateInputSerializer(serializers.Serializer):
    content = serializers.CharField()


# ---------------------------------------------------------------------------
# Output serializers
# ---------------------------------------------------------------------------


class _FkParishDisplayMixin:
    """B5c — nom de paroisse + diocèse affichés depuis la FK target_parish ; repli sur
    le texte stocké pour les demandes orphelines legacy (FK NULL)."""

    def get_parish_name(self, obj) -> str:
        if obj.target_parish_id:
            return obj.target_parish.name
        return obj.parish_name

    def get_diocese(self, obj) -> str:
        if obj.target_parish_id:
            return obj.target_parish.diocese.name
        return obj.diocese


class DocumentRequestListOutputSerializer(_FkParishDisplayMixin, serializers.ModelSerializer):
    requester_email = serializers.EmailField(source="requester.email", read_only=True)
    document_type_label = serializers.CharField(source="get_document_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    parish_name = serializers.SerializerMethodField()
    diocese = serializers.SerializerMethodField()
    # Délais : calculés côté serveur (apps.documents.sla) pour que le client
    # n'ait pas à dupliquer les seuils ni la façon de mesurer l'ancienneté.
    sla_days = serializers.SerializerMethodField()
    sla_threshold_days = serializers.SerializerMethodField()
    is_escalated = serializers.SerializerMethodField()
    # Document final déposé : exposé dès la liste pour que le coffre-fort n'ait
    # pas à charger le détail de chaque demande juste pour obtenir ce lien.
    final_document_url = serializers.SerializerMethodField()

    class Meta:
        model = DocumentRequest
        fields = [
            "id",
            "reference",
            "document_type",
            "document_type_label",
            "document_type_free",
            "reason",
            "status",
            "status_label",
            "requester_last_name",
            "requester_first_names",
            "requester_email",
            "parish_name",
            "diocese",
            "target_parish",
            "created_at",
            "updated_at",
            "sla_days",
            "sla_threshold_days",
            "is_escalated",
            "final_document_url",
        ]

    def get_sla_days(self, obj) -> int | None:
        return sla.sla_days(obj)

    def get_sla_threshold_days(self, obj) -> int | None:
        return sla.sla_threshold_days(obj.status)

    def get_is_escalated(self, obj) -> bool:
        return sla.is_escalated(obj)

    def get_final_document_url(self, obj) -> str | None:
        # `obj.attachments` est préchargé par le selector : on filtre en Python
        # pour ne pas relancer une requête par demande (N+1).
        for attachment in obj.attachments.all():
            if attachment.attachment_type != DocumentRequest.AttachmentType.PARISH_FINAL:
                continue
            if not attachment.file_id or not attachment.file.file:
                continue
            return attachment.file.url
        return None


class DocumentRequestStatusCountsOutputSerializer(serializers.Serializer):
    """Comptages par statut sur le périmètre d'autorité du demandeur."""

    counts = serializers.DictField(child=serializers.IntegerField())
    total = serializers.IntegerField()


class StatusLogOutputSerializer(serializers.ModelSerializer):
    changed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = DocumentRequestStatusLog
        fields = ["id", "from_status", "to_status", "changed_by_name", "comment", "created_at"]

    def get_changed_by_name(self, obj) -> str | None:
        if obj.changed_by is None:
            return "Système"
        return _user_display_name(obj.changed_by)


class AttachmentOutputSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    file_name = serializers.CharField(source="file.original_file_name", read_only=True)
    attachment_type_label = serializers.CharField(source="get_attachment_type_display", read_only=True)

    class Meta:
        model = DocumentRequestAttachment
        fields = [
            "id",
            "attachment_type",
            "attachment_type_label",
            "label",
            "file_url",
            "file_name",
            "created_at",
        ]

    def get_file_url(self, obj) -> str | None:
        if not obj.file_id or not obj.file.file:
            return None
        return obj.file.url


class InternalNoteOutputSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = InternalNote
        fields = ["id", "author_name", "content", "created_at"]

    def get_author_name(self, obj) -> str:
        return _user_display_name(obj.author)


class DocumentRequestDetailOutputSerializer(_FkParishDisplayMixin, serializers.ModelSerializer):
    requester_email = serializers.EmailField(source="requester.email", read_only=True)
    document_type_label = serializers.CharField(source="get_document_type_display", read_only=True)
    reason_label = serializers.CharField(source="get_reason_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    assigned_to_name = serializers.SerializerMethodField()
    parish_name = serializers.SerializerMethodField()
    diocese = serializers.SerializerMethodField()
    status_logs = StatusLogOutputSerializer(many=True, read_only=True)
    attachments = AttachmentOutputSerializer(many=True, read_only=True)

    class Meta:
        model = DocumentRequest
        fields = [
            "id",
            "reference",
            "document_type",
            "document_type_label",
            "document_type_free",
            "reason",
            "reason_label",
            "reason_free",
            "status",
            "status_label",
            "rejection_reason",
            "assigned_to_name",
            "requester_last_name",
            "requester_first_names",
            "requester_email",
            "date_of_birth",
            "place_of_birth",
            "contact_phone",
            "contact_email",
            "registered_last_name",
            "registered_first_names",
            "father_last_name",
            "mother_last_name",
            "parish_name",
            "diocese",
            "sacrament_approximate_date",
            "sacrament_location",
            "additional_info",
            "document_details",
            "consent_given",
            "status_logs",
            "attachments",
            "created_at",
            "updated_at",
        ]

    def get_assigned_to_name(self, obj) -> str | None:
        if obj.assigned_to is None:
            return None
        return _user_display_name(obj.assigned_to)


class DocumentRequestReasonOptionSerializer(serializers.Serializer):
    """Un motif de demande : valeur technique + libellé affichable."""

    value = serializers.CharField(help_text="Valeur à renvoyer dans le champ `reason`.")
    label = serializers.CharField(  # type: ignore[assignment]  # drf-stubs : collision avec l'attribut Field.label
        help_text="Libellé affichable (français)."
    )


class DocumentRequestTypeOptionSerializer(serializers.Serializer):
    """Un type de document, avec les motifs recevables pour ce type."""

    value = serializers.CharField(help_text="Valeur à renvoyer dans le champ `document_type`.")
    label = serializers.CharField(  # type: ignore[assignment]  # drf-stubs : collision avec l'attribut Field.label
        help_text="Libellé affichable (français)."
    )
    requires_precision = serializers.BooleanField(
        help_text="Si vrai, `document_type_free` est obligatoire (cas « Autre document »)."
    )
    allowed_reasons = serializers.ListField(
        child=serializers.CharField(),
        help_text="Valeurs de `reason` recevables avec ce type de document.",
    )


class DocumentRequestOptionsOutputSerializer(serializers.Serializer):
    """Référentiel du formulaire de demande — source unique de la règle type ↔ motif."""

    document_types = DocumentRequestTypeOptionSerializer(many=True)
    reasons = DocumentRequestReasonOptionSerializer(many=True)

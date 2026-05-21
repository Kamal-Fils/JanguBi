from rest_framework import serializers

from apps.messaging.models import (
    Conversation,
    ConversationExport,
    Message,
    MessageAttachment,
    MessageBlock,
    MessageReaction,
    Notification,
    PriestProfile,
)


class PriestProfileOutputSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(source="user.id", read_only=True)
    full_name = serializers.SerializerMethodField()
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = PriestProfile
        fields = [
            "id",
            "user_id",
            "full_name",
            "email",
            "accepts_pastoral_chat",
            "cgu_accepted_at",
            "ordination_year",
            "bio",
            "created_at",
        ]

    def get_full_name(self, obj) -> str:
        profile = getattr(obj.user, "profile", None)
        if profile:
            return f"{profile.first_name} {profile.last_name}".strip() or obj.user.email
        return obj.user.email


class PriestProfileCreateInputSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()


class PriestProfileUpdateInputSerializer(serializers.Serializer):
    accepts_pastoral_chat = serializers.BooleanField(required=False)
    ordination_year = serializers.IntegerField(required=False, min_value=1900, max_value=2100)
    bio = serializers.CharField(required=False, max_length=1000, allow_blank=True)


class ConversationParticipantSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.SerializerMethodField()
    email = serializers.EmailField()

    def get_full_name(self, obj) -> str:
        profile = getattr(obj, "profile", None)
        if profile:
            return f"{profile.first_name} {profile.last_name}".strip() or obj.email
        return obj.email


class ConversationOutputSerializer(serializers.ModelSerializer):
    participant_a = ConversationParticipantSerializer(read_only=True)
    participant_b = ConversationParticipantSerializer(read_only=True)
    unread_count = serializers.IntegerField(default=0)

    class Meta:
        model = Conversation
        fields = [
            "id",
            "participant_a",
            "participant_b",
            "last_message_at",
            "is_archived",
            "cgu_accepted_by_a",
            "cgu_accepted_by_b",
            "scheduled_purge_at",
            "unread_count",
            "created_at",
        ]


class ConversationCreateInputSerializer(serializers.Serializer):
    priest_user_id = serializers.UUIDField()


class MessageReactionOutputSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(source="user.id", read_only=True)

    class Meta:
        model = MessageReaction
        fields = ["id", "user_id", "emoji", "created_at"]


class MessageAttachmentOutputSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    file_name = serializers.CharField(source="file.original_file_name", read_only=True)

    class Meta:
        model = MessageAttachment
        fields = ["id", "url", "file_name"]

    def get_url(self, obj) -> str:
        return obj.file.url


class MessageOutputSerializer(serializers.ModelSerializer):
    sender_id = serializers.UUIDField(source="sender.id", read_only=True)
    sender_name = serializers.SerializerMethodField()
    reactions = MessageReactionOutputSerializer(many=True, read_only=True)
    attachments = MessageAttachmentOutputSerializer(many=True, read_only=True)
    reply_to_id = serializers.UUIDField(
        source="reply_to.id", read_only=True, allow_null=True
    )
    is_deleted = serializers.BooleanField(read_only=True)

    class Meta:
        model = Message
        fields = [
            "id",
            "sender_id",
            "sender_name",
            "content",
            "content_type",
            "client_message_id",
            "reply_to_id",
            "read_at",
            "deleted_at",
            "is_deleted",
            "reactions",
            "attachments",
            "created_at",
        ]

    def get_sender_name(self, obj) -> str:
        profile = getattr(obj.sender, "profile", None)
        if profile:
            return f"{profile.first_name} {profile.last_name}".strip() or obj.sender.email
        return obj.sender.email

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.is_deleted:
            data["content"] = None
        return data


class MessageSendInputSerializer(serializers.Serializer):
    content = serializers.CharField(max_length=4000)
    client_message_id = serializers.UUIDField(required=False, allow_null=True)
    reply_to_id = serializers.UUIDField(required=False, allow_null=True)


class MessageListInputSerializer(serializers.Serializer):
    before_id = serializers.UUIDField(required=False)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100, default=30)


class ReactInputSerializer(serializers.Serializer):
    emoji = serializers.CharField(max_length=10)


class BlockOutputSerializer(serializers.ModelSerializer):
    blocked_id = serializers.UUIDField(source="blocked.id", read_only=True)
    blocked_name = serializers.SerializerMethodField()

    class Meta:
        model = MessageBlock
        fields = ["id", "blocked_id", "blocked_name", "created_at"]

    def get_blocked_name(self, obj) -> str:
        profile = getattr(obj.blocked, "profile", None)
        if profile:
            return f"{profile.first_name} {profile.last_name}".strip() or obj.blocked.email
        return obj.blocked.email


class BlockCreateInputSerializer(serializers.Serializer):
    blocked_user_id = serializers.UUIDField()


class ExportOutputSerializer(serializers.ModelSerializer):
    json_url = serializers.SerializerMethodField()
    pdf_url = serializers.SerializerMethodField()

    class Meta:
        model = ConversationExport
        fields = ["id", "json_url", "pdf_url", "completed_at", "created_at"]

    def get_json_url(self, obj) -> str | None:
        return obj.json_file.url if obj.json_file else None

    def get_pdf_url(self, obj) -> str | None:
        return obj.pdf_file.url if obj.pdf_file else None


class NotificationOutputSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "event_type", "payload", "is_read", "read_at", "created_at"]


class ClergicalMessageSendInputSerializer(serializers.Serializer):
    subject = serializers.CharField(max_length=200)
    body = serializers.CharField()
    recipient_scope = serializers.ChoiceField(choices=[
        ("individual", "Individuel"),
        ("parish_clergy", "Clergé de la paroisse"),
        ("diocese_clergy", "Clergé du diocèse"),
        ("province_bishops", "Évêques de la province"),
    ])
    scope_id = serializers.IntegerField(required=False, allow_null=True)
    individual_recipient_id = serializers.IntegerField(required=False, allow_null=True)


class ClergicalMessageOutputSerializer(serializers.ModelSerializer):
    sender_email = serializers.EmailField(source="sender.email", read_only=True)
    recipient_email = serializers.SerializerMethodField()

    class Meta:
        from apps.messaging.models import ClergicalMessage
        model = ClergicalMessage
        fields = [
            "id", "sender_email", "recipient_scope", "scope_id",
            "recipient_email", "subject", "body", "read_at", "created_at",
        ]

    def get_recipient_email(self, obj) -> str | None:
        if obj.individual_recipient:
            return obj.individual_recipient.email
        return None

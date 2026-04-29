from django.contrib import admin

from apps.messaging.models import (
    Conversation,
    ConversationExport,
    Message,
    MessageBlock,
    MessageReaction,
    Notification,
    PriestProfile,
)


@admin.register(PriestProfile)
class PriestProfileAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "accepts_pastoral_chat", "cgu_accepted_at", "ordination_year"]
    list_filter = ["accepts_pastoral_chat"]
    search_fields = ["user__email", "user__first_name", "user__last_name"]
    raw_id_fields = ["user"]


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ["id", "participant_a", "participant_b", "last_message_at", "is_archived", "scheduled_purge_at"]
    list_filter = ["is_archived"]
    search_fields = ["participant_a__email", "participant_b__email"]
    raw_id_fields = ["participant_a", "participant_b"]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ["id", "conversation", "sender", "content_type", "read_at", "deleted_at", "created_at"]
    list_filter = ["content_type"]
    search_fields = ["sender__email"]
    raw_id_fields = ["conversation", "sender", "reply_to"]

    def get_queryset(self, request):
        # Defer encrypted content to avoid unnecessary decryption in list view
        return super().get_queryset(request).defer("content")


@admin.register(MessageBlock)
class MessageBlockAdmin(admin.ModelAdmin):
    list_display = ["id", "blocker", "blocked", "created_at"]
    raw_id_fields = ["blocker", "blocked"]


@admin.register(MessageReaction)
class MessageReactionAdmin(admin.ModelAdmin):
    list_display = ["id", "message", "user", "emoji", "created_at"]
    raw_id_fields = ["message", "user"]


@admin.register(ConversationExport)
class ConversationExportAdmin(admin.ModelAdmin):
    list_display = ["id", "conversation", "requested_by", "completed_at", "created_at"]
    raw_id_fields = ["conversation", "requested_by"]


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "event_type", "is_read", "read_at", "created_at"]
    list_filter = ["event_type", "is_read"]
    search_fields = ["user__email"]
    raw_id_fields = ["user"]

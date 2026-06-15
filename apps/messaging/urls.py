from django.urls import path

from apps.messaging.apis import (
    BlockDeleteApi,
    BlockListCreateApi,
    ClergicalMessageInboxApi,
    ClergicalMessageReadApi,
    ClergicalMessageSendApi,
    ClergicalMessageSentApi,
    ConversationArchiveApi,
    ConversationCguApi,
    ConversationCreateApi,
    ConversationDetailApi,
    ConversationExportApi,
    ConversationListApi,
    MessageDeleteApi,
    MessageListApi,
    MessageReactApi,
    MessageReadApi,
    MessageSendApi,
    NotificationListApi,
    NotificationReadApi,
    PriestListApi,
    PriestProfileCguApi,
    PriestProfileCreateApi,
    PriestProfileUpdateApi,
)

urlpatterns = [
    # Priest profiles
    path("priest-profile/", PriestProfileCreateApi.as_view(), name="priest-profile-create"),
    path("priest-profile/cgu/", PriestProfileCguApi.as_view(), name="priest-profile-cgu"),
    path("priest-profile/me/", PriestProfileUpdateApi.as_view(), name="priest-profile-update"),
    path("priests/", PriestListApi.as_view(), name="priest-list"),
    # Conversations
    path("conversations/", ConversationListApi.as_view(), name="conversation-list"),
    path("conversations/create/", ConversationCreateApi.as_view(), name="conversation-create"),
    path("conversations/<uuid:conversation_id>/cgu/", ConversationCguApi.as_view(), name="conversation-cgu"),
    path("conversations/<uuid:conversation_id>/archive/", ConversationArchiveApi.as_view(), name="conversation-archive"),
    path("conversations/<uuid:conversation_id>/", ConversationDetailApi.as_view(), name="conversation-detail"),
    path("conversations/<uuid:conversation_id>/export/", ConversationExportApi.as_view(), name="conversation-export"),
    # Messages
    path("conversations/<uuid:conversation_id>/messages/", MessageListApi.as_view(), name="message-list"),
    path("conversations/<uuid:conversation_id>/messages/send/", MessageSendApi.as_view(), name="message-send"),
    path("conversations/<uuid:conversation_id>/read/", MessageReadApi.as_view(), name="message-read"),
    path("messages/<uuid:message_id>/", MessageDeleteApi.as_view(), name="message-delete"),
    path("messages/<uuid:message_id>/react/", MessageReactApi.as_view(), name="message-react"),
    # Blocks
    path("blocks/", BlockListCreateApi.as_view(), name="block-list-create"),
    path("blocks/<uuid:block_id>/", BlockDeleteApi.as_view(), name="block-delete"),
    # Notifications
    path("notifications/", NotificationListApi.as_view(), name="notification-list"),
    path("notifications/<uuid:notification_id>/read/", NotificationReadApi.as_view(), name="notification-read"),
    # ClergicalMessage (inter-clergé)
    path("clerical/", ClergicalMessageSendApi.as_view(), name="clerical-send"),
    path("clerical/inbox/", ClergicalMessageInboxApi.as_view(), name="clerical-inbox"),
    path("clerical/sent/", ClergicalMessageSentApi.as_view(), name="clerical-sent"),
    path("clerical/<int:message_id>/read/", ClergicalMessageReadApi.as_view(), name="clerical-read"),
]

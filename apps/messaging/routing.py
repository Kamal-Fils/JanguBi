from django.urls import re_path

from apps.messaging.consumers import ConversationConsumer, NotificationConsumer

websocket_urlpatterns = [
    re_path(
        r"^ws/messaging/conversations/(?P<conversation_id>[0-9a-f-]+)/$",
        ConversationConsumer.as_asgi(),
    ),
    re_path(
        r"^ws/notifications/$",
        NotificationConsumer.as_asgi(),
    ),
]

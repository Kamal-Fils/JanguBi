from django.urls import re_path

from apps.rosary.consumers import RosaryConsumer

rosary_websocket_urlpatterns = [
    re_path(
        r"^ws/rosary/community/(?P<rosary_id>[0-9]+)/$",
        RosaryConsumer.as_asgi(),
    ),
]

"""
Montage TOP-LEVEL des notifications : /api/v1/notifications/.

Découple le client (web ET mobile React Native) du mount historique
/api/v1/messaging/notifications/ — les notifications ne sont pas qu'un concept
de messagerie (documents, purge, etc.). Les anciennes routes messaging restent
en place pour compatibilité.
"""

from django.urls import path

from apps.messaging.apis import (
    NotificationListApi,
    NotificationReadAllApi,
    NotificationReadApi,
    NotificationUnreadCountApi,
    PushDeviceApi,
)

urlpatterns = [
    path("", NotificationListApi.as_view(), name="list"),
    path("unread-count/", NotificationUnreadCountApi.as_view(), name="unread-count"),
    path("read-all/", NotificationReadAllApi.as_view(), name="read-all"),
    path("<uuid:notification_id>/read/", NotificationReadApi.as_view(), name="read"),
    # Tokens push de l'app mobile (enregistrés dès maintenant ; envoi FCM/APNs
    # à venir avec l'app React Native).
    path("devices/", PushDeviceApi.as_view(), name="devices"),
]

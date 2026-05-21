from django.urls import path

from apps.agenda.apis import (
    EventDetailApi,
    EventListCreateApi,
    EventRegisterApi,
    EventRegistrationsApi,
)

urlpatterns = [
    path("events/", EventListCreateApi.as_view(), name="event-list-create"),
    path("events/<int:event_id>/", EventDetailApi.as_view(), name="event-detail"),
    path("events/<int:event_id>/register/", EventRegisterApi.as_view(), name="event-register"),
    path("events/<int:event_id>/registrations/", EventRegistrationsApi.as_view(), name="event-registrations"),
]

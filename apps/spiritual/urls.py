from django.urls import path

from apps.spiritual.apis import (
    ReflectionDetailApi,
    ReflectionListCreateApi,
    ReflectionMyTodayApi,
    ReflectionTodayApi,
)

urlpatterns = [
    path("reflections/today/", ReflectionTodayApi.as_view(), name="reflection-today"),
    path("reflections/my-today/", ReflectionMyTodayApi.as_view(), name="reflection-my-today"),
    path("reflections/", ReflectionListCreateApi.as_view(), name="reflection-list-create"),
    path("reflections/<uuid:reflection_id>/", ReflectionDetailApi.as_view(), name="reflection-detail"),
]

from django.urls import path

from apps.dashboards.apis import (
    DioceseDashboardApi,
    FideleDashboardApi,
    MyDioceseDashboardApi,
    MyParishDashboardApi,
    ParishDashboardApi,
)

urlpatterns = [
    path("me/", FideleDashboardApi.as_view(), name="me"),
    path("my-parish/", MyParishDashboardApi.as_view(), name="my-parish"),
    path("my-diocese/", MyDioceseDashboardApi.as_view(), name="my-diocese"),
    path("parish/<int:parish_id>/", ParishDashboardApi.as_view(), name="parish"),
    path("diocese/<int:diocese_id>/", DioceseDashboardApi.as_view(), name="diocese"),
]

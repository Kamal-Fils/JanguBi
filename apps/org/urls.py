from django.urls import path

from apps.org.apis import DioceseListApi, ParishDetailApi, ParishListApi, ProvinceListApi

urlpatterns = [
    path("provinces/", ProvinceListApi.as_view(), name="province-list"),
    path("dioceses/", DioceseListApi.as_view(), name="diocese-list"),
    path("parishes/", ParishListApi.as_view(), name="parish-list"),
    path("parishes/<int:parish_id>/", ParishDetailApi.as_view(), name="parish-detail"),
]

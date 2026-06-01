from django.urls import path

from apps.org.apis import (
    ChurchDetailApi,
    ChurchListApi,
    DeaneryListApi,
    DioceseListApi,
    ParishDetailApi,
    ParishListApi,
    ProvinceListApi,
)

urlpatterns = [
    path("provinces/", ProvinceListApi.as_view(), name="province-list"),
    path("dioceses/", DioceseListApi.as_view(), name="diocese-list"),
    path("parishes/", ParishListApi.as_view(), name="parish-list"),
    path("parishes/<int:parish_id>/", ParishDetailApi.as_view(), name="parish-detail"),
    path("churches/", ChurchListApi.as_view(), name="church-list"),
    path("churches/<int:church_id>/", ChurchDetailApi.as_view(), name="church-detail"),
    path("deaneries/", DeaneryListApi.as_view(), name="deanery-list"),
]

from django.urls import path

from apps.org.apis import (
    ChurchDetailApi,
    ChurchListApi,
    DeaneryDetailApi,
    DeaneryListApi,
    DioceseDetailApi,
    DioceseListApi,
    ParishDetailApi,
    ParishListApi,
    ProvinceDetailApi,
    ProvinceListApi,
)

urlpatterns = [
    path("provinces/", ProvinceListApi.as_view(), name="province-list"),
    path("provinces/<int:province_id>/", ProvinceDetailApi.as_view(), name="province-detail"),
    path("dioceses/", DioceseListApi.as_view(), name="diocese-list"),
    path("dioceses/<int:diocese_id>/", DioceseDetailApi.as_view(), name="diocese-detail"),
    path("parishes/", ParishListApi.as_view(), name="parish-list"),
    path("parishes/<int:parish_id>/", ParishDetailApi.as_view(), name="parish-detail"),
    path("churches/", ChurchListApi.as_view(), name="church-list"),
    path("churches/<int:church_id>/", ChurchDetailApi.as_view(), name="church-detail"),
    path("deaneries/", DeaneryListApi.as_view(), name="deanery-list"),
    path("deaneries/<int:deanery_id>/", DeaneryDetailApi.as_view(), name="deanery-detail"),
]

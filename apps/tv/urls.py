from django.urls import path

from apps.tv.apis import CategoryDetailApi, CategoryListApi, VideoDetailApi, VideoListApi

urlpatterns = [
    path("categories/", CategoryListApi.as_view(), name="tv-category-list"),
    path("categories/<slug:slug>/", CategoryDetailApi.as_view(), name="tv-category-detail"),
    path("videos/", VideoListApi.as_view(), name="tv-video-list"),
    path("videos/<int:video_id>/", VideoDetailApi.as_view(), name="tv-video-detail"),
]

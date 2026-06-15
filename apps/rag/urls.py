from django.urls import path

from apps.rag.views import RagChatApi

urlpatterns = [
    path("query/", RagChatApi.as_view(), name="query"),
]

from django.urls import path

from .apis import (
    TriggerErrorApi,
    TriggerUnhandledExceptionApi,
)

urlpatterns = [
    path("trigger/", TriggerErrorApi.as_view()),
    path("trigger/exception/", TriggerUnhandledExceptionApi.as_view()),
]

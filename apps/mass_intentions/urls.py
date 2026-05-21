from django.urls import path

from . import apis

urlpatterns = [
    path("submit/", apis.MassIntentionSubmitApi.as_view(), name="submit"),
    path("my/", apis.MassIntentionMyListApi.as_view(), name="my-list"),
    path("parish/", apis.MassIntentionParishListApi.as_view(), name="parish-list"),
    path("<int:intention_id>/accept/", apis.MassIntentionAcceptApi.as_view(), name="accept"),
    path(
        "<int:intention_id>/propose-date/",
        apis.MassIntentionProposeDateApi.as_view(),
        name="propose-date",
    ),
    path(
        "<int:intention_id>/celebrate/",
        apis.MassIntentionCelebrateApi.as_view(),
        name="celebrate",
    ),
    path(
        "<int:intention_id>/decline/",
        apis.MassIntentionDeclineApi.as_view(),
        name="decline",
    ),
]

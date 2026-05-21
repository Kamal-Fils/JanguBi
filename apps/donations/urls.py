from django.urls import path

from . import apis

urlpatterns = [
    path("campaigns/", apis.CampaignListCreateApi.as_view(), name="campaign-list-create"),
    path("donate/", apis.DonationMakeApi.as_view(), name="donate"),
    path("my/", apis.DonationMyListApi.as_view(), name="my-list"),
]

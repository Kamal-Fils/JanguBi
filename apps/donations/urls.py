from django.urls import path

from . import apis

urlpatterns = [
    path("campaigns/", apis.CampaignListCreateApi.as_view(), name="campaign-list-create"),
    path("donate/", apis.DonationMakeApi.as_view(), name="donate"),
    path("<int:donation_id>/confirm/", apis.DonationConfirmApi.as_view(), name="confirm"),
    path("my/", apis.DonationMyListApi.as_view(), name="my-list"),
]

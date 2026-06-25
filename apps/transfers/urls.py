from django.urls import path

from . import apis

urlpatterns = [
    path("", apis.TransferCreateApi.as_view(), name="create"),
    path("my-request/", apis.TransferMyRequestApi.as_view(), name="my-request"),
    path("admin/", apis.TransferAdminListApi.as_view(), name="admin-list"),
    path("<int:transfer_id>/approve/", apis.TransferApproveApi.as_view(), name="approve"),
    path("<int:transfer_id>/reject/", apis.TransferRejectApi.as_view(), name="reject"),
    path(
        "<int:transfer_id>/acknowledge/",
        apis.TransferAcknowledgeApi.as_view(),
        name="acknowledge",
    ),
]

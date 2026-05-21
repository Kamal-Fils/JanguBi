from django.urls import path

from . import apis

urlpatterns = [
    path("invitations/", apis.InvitationListCreateApi.as_view(), name="invitations-list-create"),
    path("invitations/validate/", apis.InvitationValidateTokenApi.as_view(), name="invitations-validate"),
    path("invitations/accept/", apis.InvitationAcceptApi.as_view(), name="invitations-accept"),
    path("invitations/<int:invitation_id>/", apis.InvitationDetailApi.as_view(), name="invitations-detail"),
    path("invitations/<int:invitation_id>/revoke/", apis.InvitationRevokeApi.as_view(), name="invitations-revoke"),
]

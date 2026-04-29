from django.urls import path

from apps.documents.apis import (
    AdminDepositApi,
    AdminDocumentRequestDetailApi,
    AdminDocumentRequestListApi,
    AdminLogsApi,
    AdminNotesApi,
    AdminRejectApi,
    AdminRequestInfoApi,
    AdminStartVerificationApi,
    AdminValidateApi,
    DocumentRequestDetailApi,
    DocumentRequestListCreateApi,
    DocumentRequestSupplementApi,
)

urlpatterns = [
    # Fidèle
    path("requests/", DocumentRequestListCreateApi.as_view(), name="document-request-list-create"),
    path("requests/<uuid:request_id>/", DocumentRequestDetailApi.as_view(), name="document-request-detail"),
    path("requests/<uuid:request_id>/supplement/", DocumentRequestSupplementApi.as_view(), name="document-request-supplement"),
    # Admin back-office
    path("admin/requests/", AdminDocumentRequestListApi.as_view(), name="admin-document-request-list"),
    path("admin/requests/<uuid:request_id>/", AdminDocumentRequestDetailApi.as_view(), name="admin-document-request-detail"),
    path("admin/requests/<uuid:request_id>/start-verification/", AdminStartVerificationApi.as_view(), name="admin-document-start-verification"),
    path("admin/requests/<uuid:request_id>/request-info/", AdminRequestInfoApi.as_view(), name="admin-document-request-info"),
    path("admin/requests/<uuid:request_id>/validate/", AdminValidateApi.as_view(), name="admin-document-validate"),
    path("admin/requests/<uuid:request_id>/reject/", AdminRejectApi.as_view(), name="admin-document-reject"),
    path("admin/requests/<uuid:request_id>/deposit/", AdminDepositApi.as_view(), name="admin-document-deposit"),
    path("admin/requests/<uuid:request_id>/notes/", AdminNotesApi.as_view(), name="admin-document-notes"),
    path("admin/requests/<uuid:request_id>/logs/", AdminLogsApi.as_view(), name="admin-document-logs"),
]

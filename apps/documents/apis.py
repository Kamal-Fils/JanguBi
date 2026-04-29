from uuid import UUID

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.mixins import ApiAuthMixin
from apps.api.pagination import LimitOffsetPagination, get_paginated_response
from apps.core.exceptions import ApplicationError
from apps.documents.models import DocumentRequest
from apps.documents.permissions import IsDocumentRequester, IsDocumentRequesterOrAdmin
from apps.documents.selectors import (
    document_request_get,
    document_request_internal_note_list,
    document_request_list,
    document_request_status_log_list,
)
from apps.documents.serializers import (
    DepositDocumentInputSerializer,
    DocumentRequestCreateInputSerializer,
    DocumentRequestDetailOutputSerializer,
    DocumentRequestListOutputSerializer,
    DocumentRequestSupplementInputSerializer,
    InternalNoteCreateInputSerializer,
    InternalNoteOutputSerializer,
    RejectInputSerializer,
    StatusActionWithCommentInputSerializer,
    StatusLogOutputSerializer,
)
from apps.documents.services import (
    document_request_add_internal_note,
    document_request_create,
    document_request_deposit_document,
    document_request_reject,
    document_request_request_info,
    document_request_start_verification,
    document_request_submit_supplement,
    document_request_validate,
)
from apps.users.permissions import IsAnyAdmin


def _error(exc: ApplicationError) -> Response:
    return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Côté fidèle
# ---------------------------------------------------------------------------


class DocumentRequestListCreateApi(ApiAuthMixin, APIView):
    class Pagination(LimitOffsetPagination):
        default_limit = 20

    @extend_schema(responses={200: DocumentRequestListOutputSerializer(many=True)})
    def get(self, request):
        filters = {
            k: v
            for k, v in request.query_params.items()
            if k in ("status", "document_type", "parish_name", "search")
        }
        qs = document_request_list(user=request.user, filters=filters)
        return get_paginated_response(
            pagination_class=self.Pagination,
            serializer_class=DocumentRequestListOutputSerializer,
            queryset=qs,
            request=request,
            view=self,
        )

    @extend_schema(
        request=DocumentRequestCreateInputSerializer,
        responses={201: DocumentRequestDetailOutputSerializer},
    )
    def post(self, request):
        serializer = DocumentRequestCreateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            req = document_request_create(
                requester=request.user, data=dict(serializer.validated_data)
            )
        except ApplicationError as exc:
            return _error(exc)
        return Response(
            DocumentRequestDetailOutputSerializer(req).data,
            status=status.HTTP_201_CREATED,
        )


class DocumentRequestDetailApi(ApiAuthMixin, APIView):
    def get_permissions(self):
        return [IsAuthenticated(), IsDocumentRequesterOrAdmin()]

    @extend_schema(responses={200: DocumentRequestDetailOutputSerializer})
    def get(self, request, request_id: UUID):
        try:
            req = document_request_get(request_id=request_id, user=request.user)
        except ApplicationError as exc:
            return _error(exc)
        self.check_object_permissions(request, req)
        return Response(DocumentRequestDetailOutputSerializer(req).data)


class DocumentRequestSupplementApi(ApiAuthMixin, APIView):
    def get_permissions(self):
        return [IsAuthenticated(), IsDocumentRequester()]

    @extend_schema(
        request=DocumentRequestSupplementInputSerializer,
        responses={200: DocumentRequestDetailOutputSerializer},
    )
    def post(self, request, request_id: UUID):
        req = get_object_or_404(DocumentRequest, pk=request_id)
        self.check_object_permissions(request, req)
        if req.status != DocumentRequest.Status.INFO_REQUESTED:
            return Response(
                {"detail": "Un complément n'est possible que si le statut est 'info_requested'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = DocumentRequestSupplementInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            req = document_request_submit_supplement(
                request_obj=req,
                requester=request.user,
                data=dict(serializer.validated_data),
            )
        except ApplicationError as exc:
            return _error(exc)
        return Response(DocumentRequestDetailOutputSerializer(req).data)


# ---------------------------------------------------------------------------
# Back-office paroisse / admin
# ---------------------------------------------------------------------------


class AdminDocumentRequestListApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsAnyAdmin]

    class Pagination(LimitOffsetPagination):
        default_limit = 20

    @extend_schema(responses={200: DocumentRequestListOutputSerializer(many=True)})
    def get(self, request):
        filters = {
            k: v
            for k, v in request.query_params.items()
            if k in ("status", "document_type", "parish_name", "search", "assigned_to_id")
        }
        qs = document_request_list(user=request.user, filters=filters)
        return get_paginated_response(
            pagination_class=self.Pagination,
            serializer_class=DocumentRequestListOutputSerializer,
            queryset=qs,
            request=request,
            view=self,
        )


class AdminDocumentRequestDetailApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsAnyAdmin]

    @extend_schema(responses={200: DocumentRequestDetailOutputSerializer})
    def get(self, request, request_id: UUID):
        req = document_request_get(request_id=request_id, user=request.user)
        return Response(DocumentRequestDetailOutputSerializer(req).data)


class AdminStartVerificationApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsAnyAdmin]

    @extend_schema(responses={200: DocumentRequestDetailOutputSerializer})
    def post(self, request, request_id: UUID):
        req = get_object_or_404(DocumentRequest, pk=request_id)
        try:
            req = document_request_start_verification(request_obj=req, agent=request.user)
        except ApplicationError as exc:
            return _error(exc)
        return Response(DocumentRequestDetailOutputSerializer(req).data)


class AdminRequestInfoApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsAnyAdmin]

    @extend_schema(
        request=StatusActionWithCommentInputSerializer,
        responses={200: DocumentRequestDetailOutputSerializer},
    )
    def post(self, request, request_id: UUID):
        req = get_object_or_404(DocumentRequest, pk=request_id)
        serializer = StatusActionWithCommentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            req = document_request_request_info(
                request_obj=req,
                agent=request.user,
                comment=serializer.validated_data["comment"],
            )
        except ApplicationError as exc:
            return _error(exc)
        return Response(DocumentRequestDetailOutputSerializer(req).data)


class AdminValidateApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsAnyAdmin]

    @extend_schema(responses={200: DocumentRequestDetailOutputSerializer})
    def post(self, request, request_id: UUID):
        req = get_object_or_404(DocumentRequest, pk=request_id)
        try:
            req = document_request_validate(request_obj=req, agent=request.user)
        except ApplicationError as exc:
            return _error(exc)
        return Response(DocumentRequestDetailOutputSerializer(req).data)


class AdminRejectApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsAnyAdmin]

    @extend_schema(
        request=RejectInputSerializer,
        responses={200: DocumentRequestDetailOutputSerializer},
    )
    def post(self, request, request_id: UUID):
        req = get_object_or_404(DocumentRequest, pk=request_id)
        serializer = RejectInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            req = document_request_reject(
                request_obj=req,
                agent=request.user,
                reason=serializer.validated_data["reason"],
            )
        except ApplicationError as exc:
            return _error(exc)
        return Response(DocumentRequestDetailOutputSerializer(req).data)


class AdminDepositApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsAnyAdmin]

    @extend_schema(
        request=DepositDocumentInputSerializer,
        responses={200: DocumentRequestDetailOutputSerializer},
    )
    def post(self, request, request_id: UUID):
        req = get_object_or_404(DocumentRequest, pk=request_id)
        serializer = DepositDocumentInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            req = document_request_deposit_document(
                request_obj=req,
                agent=request.user,
                file_id=serializer.validated_data["file_id"],
                label=serializer.validated_data.get("label", "Document officiel"),
            )
        except ApplicationError as exc:
            return _error(exc)
        return Response(DocumentRequestDetailOutputSerializer(req).data)


class AdminNotesApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsAnyAdmin]

    @extend_schema(responses={200: InternalNoteOutputSerializer(many=True)})
    def get(self, request, request_id: UUID):
        req = get_object_or_404(DocumentRequest, pk=request_id)
        notes = document_request_internal_note_list(request_obj=req)
        return Response(InternalNoteOutputSerializer(notes, many=True).data)

    @extend_schema(
        request=InternalNoteCreateInputSerializer,
        responses={201: InternalNoteOutputSerializer},
    )
    def post(self, request, request_id: UUID):
        req = get_object_or_404(DocumentRequest, pk=request_id)
        serializer = InternalNoteCreateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = document_request_add_internal_note(
            request_obj=req,
            author=request.user,
            content=serializer.validated_data["content"],
        )
        return Response(InternalNoteOutputSerializer(note).data, status=status.HTTP_201_CREATED)


class AdminLogsApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsAnyAdmin]

    @extend_schema(responses={200: StatusLogOutputSerializer(many=True)})
    def get(self, request, request_id: UUID):
        req = get_object_or_404(DocumentRequest, pk=request_id)
        logs = document_request_status_log_list(request_obj=req)
        return Response(StatusLogOutputSerializer(logs, many=True).data)

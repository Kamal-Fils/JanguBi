from uuid import UUID

from django.shortcuts import get_object_or_404
from drf_spectacular.openapi import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.mixins import ApiAuthMixin
from apps.api.pagination import (
    LimitOffsetPagination,
    get_paginated_response,
    paginated_response_serializer,
)
from apps.core.exceptions import ApplicationError
from apps.documents.models import DocumentRequest
from apps.documents.permissions import IsDocumentRequester, IsDocumentRequesterOrAdmin
from apps.documents.selectors import (
    document_request_get,
    document_request_get_for_admin,
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
from apps.users.permissions import IsAnyAdmin, IsOnboardingCompleted


def _error(exc: ApplicationError) -> Response:
    return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Côté fidèle
# ---------------------------------------------------------------------------


class DocumentRequestListCreateApi(ApiAuthMixin, APIView):
    class Pagination(LimitOffsetPagination):
        default_limit = 20

    def get_permissions(self):
        # GET (lister ses demandes) : authentification suffit. POST (créer une
        # demande = écriture territoriale) : onboarding finalisé requis (A1).
        if self.request.method == "POST":
            return [IsAuthenticated(), IsOnboardingCompleted()]
        return [IsAuthenticated()]

    @extend_schema(
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT, description="Nombre de résultats (défaut 20)"),
            OpenApiParameter("offset", OpenApiTypes.INT, description="Décalage pagination"),
            OpenApiParameter("status", OpenApiTypes.STR, enum=["submitted", "under_verification", "validated", "info_requested", "rejected", "document_deposited"], description="Filtrer par statut"),
            OpenApiParameter("document_type", OpenApiTypes.STR, description="Filtrer par type de document"),
            OpenApiParameter("parish_name", OpenApiTypes.STR, description="Filtrer par nom de paroisse"),
            OpenApiParameter("search", OpenApiTypes.STR, description="Recherche textuelle"),
        ],
        responses={200: paginated_response_serializer(DocumentRequestListOutputSerializer)},
        tags=["documents"],
        summary="Lister mes demandes de document",
    )
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
        tags=["documents"],
        summary="Créer une demande de document",
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

    @extend_schema(
        responses={200: DocumentRequestDetailOutputSerializer},
        tags=["documents"],
        summary="Détail d'une demande de document",
    )
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
        tags=["documents"],
        summary="Soumettre un complément d'information",
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

    @extend_schema(
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT, description="Nombre de résultats (défaut 20)"),
            OpenApiParameter("offset", OpenApiTypes.INT, description="Décalage pagination"),
            OpenApiParameter("status", OpenApiTypes.STR, enum=["submitted", "under_verification", "validated", "info_requested", "rejected", "document_deposited"], description="Filtrer par statut"),
            OpenApiParameter("document_type", OpenApiTypes.STR, description="Filtrer par type de document"),
            OpenApiParameter("parish_name", OpenApiTypes.STR, description="Filtrer par nom de paroisse"),
            OpenApiParameter("search", OpenApiTypes.STR, description="Recherche textuelle"),
            OpenApiParameter("assigned_to_id", OpenApiTypes.INT, description="Filtrer par agent assigné"),
        ],
        responses={200: paginated_response_serializer(DocumentRequestListOutputSerializer)},
        tags=["documents"],
        summary="Lister toutes les demandes (admin)",
    )
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

    @extend_schema(
        responses={200: DocumentRequestDetailOutputSerializer},
        tags=["documents"],
        summary="Détail d'une demande (admin)",
    )
    def get(self, request, request_id: UUID):
        req = document_request_get_for_admin(request_id=request_id, user=request.user)
        return Response(DocumentRequestDetailOutputSerializer(req).data)


class AdminStartVerificationApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsAnyAdmin]

    @extend_schema(
        responses={200: DocumentRequestDetailOutputSerializer},
        tags=["documents"],
        summary="Démarrer la vérification (admin)",
    )
    def post(self, request, request_id: UUID):
        req = document_request_get_for_admin(request_id=request_id, user=request.user)
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
        tags=["documents"],
        summary="Demander un complément d'information (admin)",
    )
    def post(self, request, request_id: UUID):
        req = document_request_get_for_admin(request_id=request_id, user=request.user)
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

    @extend_schema(
        responses={200: DocumentRequestDetailOutputSerializer},
        tags=["documents"],
        summary="Valider une demande (admin)",
    )
    def post(self, request, request_id: UUID):
        req = document_request_get_for_admin(request_id=request_id, user=request.user)
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
        tags=["documents"],
        summary="Rejeter une demande (admin)",
    )
    def post(self, request, request_id: UUID):
        req = document_request_get_for_admin(request_id=request_id, user=request.user)
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
        tags=["documents"],
        summary="Déposer le document final (admin)",
    )
    def post(self, request, request_id: UUID):
        req = document_request_get_for_admin(request_id=request_id, user=request.user)
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

    @extend_schema(
        responses={200: InternalNoteOutputSerializer(many=True)},
        tags=["documents"],
        summary="Lister les notes internes (admin)",
    )
    def get(self, request, request_id: UUID):
        req = document_request_get_for_admin(request_id=request_id, user=request.user)
        notes = document_request_internal_note_list(request_obj=req)
        return Response(InternalNoteOutputSerializer(notes, many=True).data)

    @extend_schema(
        request=InternalNoteCreateInputSerializer,
        responses={201: InternalNoteOutputSerializer},
        tags=["documents"],
        summary="Ajouter une note interne (admin)",
    )
    def post(self, request, request_id: UUID):
        req = document_request_get_for_admin(request_id=request_id, user=request.user)
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

    @extend_schema(
        responses={200: StatusLogOutputSerializer(many=True)},
        tags=["documents"],
        summary="Historique des statuts (admin)",
    )
    def get(self, request, request_id: UUID):
        req = document_request_get_for_admin(request_id=request_id, user=request.user)
        logs = document_request_status_log_list(request_obj=req)
        return Response(StatusLogOutputSerializer(logs, many=True).data)

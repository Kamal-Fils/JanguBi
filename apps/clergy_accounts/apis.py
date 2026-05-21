from drf_spectacular.utils import OpenApiParameter, extend_schema
from drf_spectacular.openapi import OpenApiTypes
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.mixins import ApiAuthMixin
from apps.api.pagination import LimitOffsetPagination, get_paginated_response
from apps.core.exceptions import ApplicationError
from apps.users.enums import PastoralRole, UserRole

from .models import ClergicalInvitation
from .selectors import invitation_get_by_token, invitation_list
from .serializers import (
    InvitationAcceptInputSerializer,
    InvitationCreateInputSerializer,
    InvitationOutputSerializer,
)
from .services import invitation_accept, invitation_create, invitation_revoke


def _error(exc: ApplicationError) -> Response:
    return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)


def _can_manage_invitations(user) -> bool:
    if user.role == UserRole.SUPER_ADMIN:
        return True
    return user.pastoral_role in (PastoralRole.EVEQUE, PastoralRole.ARCHEVEQUE)


class InvitationListCreateApi(ApiAuthMixin, APIView):
    @extend_schema(
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT, description="Nombre de résultats"),
            OpenApiParameter("offset", OpenApiTypes.INT, description="Offset de pagination"),
            OpenApiParameter(
                "status",
                OpenApiTypes.STR,
                enum=["pending", "accepted", "revoked", "expired"],
                description="Filtrer par statut",
            ),
        ],
        responses={200: InvitationOutputSerializer(many=True)},
        tags=["clergy-accounts"],
        summary="Lister les invitations clergé",
    )
    def get(self, request):
        if not _can_manage_invitations(request.user):
            return Response({"detail": "Accès non autorisé."}, status=status.HTTP_403_FORBIDDEN)

        status_filter = request.query_params.get("status")
        invitations = invitation_list(created_by=request.user, status=status_filter)

        return get_paginated_response(
            pagination_class=LimitOffsetPagination,
            serializer_class=InvitationOutputSerializer,
            queryset=invitations,
            request=request,
            view=self,
        )

    @extend_schema(
        request=InvitationCreateInputSerializer,
        responses={201: InvitationOutputSerializer},
        tags=["clergy-accounts"],
        summary="Créer une invitation clergé",
    )
    def post(self, request):
        if not _can_manage_invitations(request.user):
            return Response({"detail": "Accès non autorisé."}, status=status.HTTP_403_FORBIDDEN)

        serializer = InvitationCreateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            invitation = invitation_create(inviter=request.user, **serializer.validated_data)
        except ApplicationError as exc:
            return _error(exc)

        return Response(InvitationOutputSerializer(invitation).data, status=status.HTTP_201_CREATED)


class InvitationDetailApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: InvitationOutputSerializer},
        tags=["clergy-accounts"],
        summary="Détail d'une invitation",
    )
    def get(self, request, invitation_id: int):
        if not _can_manage_invitations(request.user):
            return Response({"detail": "Accès non autorisé."}, status=status.HTTP_403_FORBIDDEN)

        try:
            invitation = ClergicalInvitation.objects.get(pk=invitation_id, created_by=request.user)
        except ClergicalInvitation.DoesNotExist:
            return Response({"detail": "Invitation introuvable."}, status=status.HTTP_404_NOT_FOUND)

        return Response(InvitationOutputSerializer(invitation).data)


class InvitationRevokeApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: InvitationOutputSerializer},
        tags=["clergy-accounts"],
        summary="Révoquer une invitation",
    )
    def post(self, request, invitation_id: int):
        if not _can_manage_invitations(request.user):
            return Response({"detail": "Accès non autorisé."}, status=status.HTTP_403_FORBIDDEN)

        try:
            inv = ClergicalInvitation.objects.get(pk=invitation_id, created_by=request.user)
        except ClergicalInvitation.DoesNotExist:
            return Response({"detail": "Invitation introuvable."}, status=status.HTTP_404_NOT_FOUND)

        try:
            inv = invitation_revoke(invitation=inv, revoker=request.user)
        except ApplicationError as exc:
            return _error(exc)

        return Response(InvitationOutputSerializer(inv).data)


class InvitationValidateTokenApi(APIView):
    """Public endpoint — validates token and returns invitation details (no auth required)."""

    @extend_schema(
        parameters=[
            OpenApiParameter("token", OpenApiTypes.UUID, location="query", description="UUID du token d'invitation"),
        ],
        responses={200: InvitationOutputSerializer},
        tags=["clergy-accounts"],
        summary="Valider un token d'invitation (public)",
    )
    def get(self, request):
        token = request.query_params.get("token")
        if not token:
            return Response({"detail": "Token manquant."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            invitation = invitation_get_by_token(token=token)
        except ApplicationError as exc:
            return _error(exc)

        if not invitation.is_valid:
            return Response({"detail": "Invitation expirée ou invalide."}, status=status.HTTP_410_GONE)

        return Response(InvitationOutputSerializer(invitation).data)


class InvitationAcceptApi(ApiAuthMixin, APIView):
    @extend_schema(
        request=InvitationAcceptInputSerializer,
        responses={200: InvitationOutputSerializer},
        tags=["clergy-accounts"],
        summary="Accepter une invitation (utilisateur connecté)",
    )
    def post(self, request):
        serializer = InvitationAcceptInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token = str(serializer.validated_data["token"])

        try:
            invitation = invitation_accept(token=token, user=request.user)
        except ApplicationError as exc:
            return _error(exc)

        return Response(InvitationOutputSerializer(invitation).data)

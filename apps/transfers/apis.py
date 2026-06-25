from drf_spectacular.openapi import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.mixins import ApiAuthMixin
from apps.api.pagination import LimitOffsetPagination, get_paginated_response, paginated_response_serializer
from apps.core.exceptions import ApplicationError
from apps.org.selectors import parish_get_by_id
from apps.users.permissions import IsAnyAdmin, IsOnboardingCompleted

from .selectors import (
    transfer_get_by_id,
    transfer_get_my,
    transfer_list_for_admin,
)
from .serializers import (
    TransferCreateInputSerializer,
    TransferOutputSerializer,
    TransferRejectInputSerializer,
)
from .services import (
    transfer_acknowledge,
    transfer_approve,
    transfer_create,
    transfer_reject,
)


def _error(exc: ApplicationError) -> Response:
    return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)


def _forbidden(message: str = "Vous n'administrez pas cette paroisse.") -> Response:
    return Response({"detail": message}, status=status.HTTP_403_FORBIDDEN)


class TransferCreateApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsOnboardingCompleted]  # écriture territoriale

    @extend_schema(
        request=TransferCreateInputSerializer,
        responses={201: TransferOutputSerializer},
        tags=["transfers"],
        summary="Soumettre une demande de transfert paroissial",
    )
    def post(self, request):
        serializer = TransferCreateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            destination_parish = parish_get_by_id(parish_id=data["destination_parish_id"])
            transfer = transfer_create(
                requester=request.user,
                destination_parish=destination_parish,
                reason=data.get("reason", ""),
            )
        except ApplicationError as e:
            return _error(e)
        return Response(
            TransferOutputSerializer(transfer).data, status=status.HTTP_201_CREATED
        )


class TransferMyRequestApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: TransferOutputSerializer},
        tags=["transfers"],
        summary="Ma demande de transfert courante (404 si aucune)",
    )
    def get(self, request):
        try:
            transfer = transfer_get_my(requester=request.user)
        except ApplicationError:
            return Response(
                {"detail": "Aucune demande de transfert."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(TransferOutputSerializer(transfer).data)


class TransferAdminListApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsAnyAdmin]

    @extend_schema(
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT),
            OpenApiParameter("offset", OpenApiTypes.INT),
        ],
        responses={200: paginated_response_serializer(TransferOutputSerializer)},
        tags=["transfers"],
        summary="Transferts des paroisses administrées (paginé)",
    )
    def get(self, request):
        transfers = transfer_list_for_admin(user=request.user)
        return get_paginated_response(
            pagination_class=LimitOffsetPagination,
            serializer_class=TransferOutputSerializer,
            queryset=transfers,
            request=request,
            view=self,
        )


class TransferApproveApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsAnyAdmin]

    @extend_schema(
        responses={200: TransferOutputSerializer},
        tags=["transfers"],
        summary="Approuver un transfert (admin paroisse d'origine)",
    )
    def post(self, request, transfer_id: int):
        from apps.users.scoping import user_can_admin_parish

        try:
            transfer = transfer_get_by_id(transfer_id=transfer_id)
        except ApplicationError as e:
            return _error(e)

        if transfer.origin_parish_id is None or not user_can_admin_parish(
            request.user, transfer.origin_parish_id
        ):
            return _forbidden("Vous n'administrez pas la paroisse d'origine.")

        try:
            transfer = transfer_approve(transfer=transfer)
        except ApplicationError as e:
            return _error(e)
        return Response(TransferOutputSerializer(transfer).data)


class TransferRejectApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsAnyAdmin]

    @extend_schema(
        request=TransferRejectInputSerializer,
        responses={200: TransferOutputSerializer},
        tags=["transfers"],
        summary="Rejeter un transfert (admin paroisse d'origine)",
    )
    def post(self, request, transfer_id: int):
        from apps.users.scoping import user_can_admin_parish

        serializer = TransferRejectInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            transfer = transfer_get_by_id(transfer_id=transfer_id)
        except ApplicationError as e:
            return _error(e)

        if transfer.origin_parish_id is None or not user_can_admin_parish(
            request.user, transfer.origin_parish_id
        ):
            return _forbidden("Vous n'administrez pas la paroisse d'origine.")

        try:
            transfer = transfer_reject(
                transfer=transfer, reason=serializer.validated_data["reason"]
            )
        except ApplicationError as e:
            return _error(e)
        return Response(TransferOutputSerializer(transfer).data)


class TransferAcknowledgeApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsAnyAdmin]

    @extend_schema(
        responses={200: TransferOutputSerializer},
        tags=["transfers"],
        summary="Accuser réception et finaliser un transfert (admin destination)",
    )
    def post(self, request, transfer_id: int):
        from apps.users.scoping import user_can_admin_parish

        try:
            transfer = transfer_get_by_id(transfer_id=transfer_id)
        except ApplicationError as e:
            return _error(e)

        if transfer.destination_parish_id is None or not user_can_admin_parish(
            request.user, transfer.destination_parish_id
        ):
            return _forbidden("Vous n'administrez pas la paroisse de destination.")

        try:
            transfer = transfer_acknowledge(transfer=transfer)
        except ApplicationError as e:
            return _error(e)
        return Response(TransferOutputSerializer(transfer).data)

from drf_spectacular.openapi import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.mixins import ApiAuthMixin
from apps.api.pagination import LimitOffsetPagination, get_paginated_response
from apps.core.exceptions import ApplicationError
from apps.users.permissions import IsOnboardingCompleted

from .selectors import (
    mass_intention_get,
    mass_intention_list_for_requestor,
    mass_intention_list_pending,
)
from .serializers import (
    MassIntentionDeclineInputSerializer,
    MassIntentionOutputSerializer,
    MassIntentionProposeDateInputSerializer,
    MassIntentionSubmitInputSerializer,
)
from .services import (
    mass_intention_accept,
    mass_intention_celebrate,
    mass_intention_decline,
    mass_intention_propose_date,
    mass_intention_submit,
)

CLERGY_ROLES = {"pretre", "eveque", "archeveque"}


def _error(exc: ApplicationError) -> Response:
    return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)


class MassIntentionSubmitApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsOnboardingCompleted]  # A1 — écriture territoriale

    @extend_schema(
        request=MassIntentionSubmitInputSerializer,
        responses={201: MassIntentionOutputSerializer},
        tags=["mass-intentions"],
        summary="Soumettre une intention de messe",
    )
    def post(self, request):
        serializer = MassIntentionSubmitInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        parish = None
        if data.get("parish_id"):
            from apps.org.models import Parish

            try:
                parish = Parish.objects.get(id=data["parish_id"])
            except Parish.DoesNotExist:
                return Response(
                    {"detail": "Paroisse introuvable."}, status=status.HTTP_400_BAD_REQUEST
                )
        try:
            intention = mass_intention_submit(
                requestor=request.user,
                intention_type=data["intention_type"],
                intention_text=data["intention_text"],
                parish=parish,
            )
        except ApplicationError as e:
            return _error(e)
        return Response(
            MassIntentionOutputSerializer(intention).data, status=status.HTTP_201_CREATED
        )


class MassIntentionMyListApi(ApiAuthMixin, APIView):
    @extend_schema(
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT),
            OpenApiParameter("offset", OpenApiTypes.INT),
        ],
        responses={200: MassIntentionOutputSerializer(many=True)},
        tags=["mass-intentions"],
        summary="Mes intentions de messe (fidèle)",
    )
    def get(self, request):
        intentions = mass_intention_list_for_requestor(requestor=request.user)
        return get_paginated_response(
            pagination_class=LimitOffsetPagination,
            serializer_class=MassIntentionOutputSerializer,
            queryset=intentions,
            request=request,
            view=self,
        )


class MassIntentionParishListApi(ApiAuthMixin, APIView):
    @extend_schema(
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT),
            OpenApiParameter("offset", OpenApiTypes.INT),
        ],
        responses={200: MassIntentionOutputSerializer(many=True)},
        tags=["mass-intentions"],
        summary="Intentions de la paroisse (prêtre)",
    )
    def get(self, request):
        if getattr(request.user, "pastoral_role", None) not in CLERGY_ROLES:
            return Response(
                {"detail": "Accès réservé au clergé."},
                status=status.HTTP_403_FORBIDDEN,
            )
        intentions = mass_intention_list_pending(pretre=request.user)
        return get_paginated_response(
            pagination_class=LimitOffsetPagination,
            serializer_class=MassIntentionOutputSerializer,
            queryset=intentions,
            request=request,
            view=self,
        )


class MassIntentionAcceptApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: MassIntentionOutputSerializer},
        tags=["mass-intentions"],
        summary="Accepter une intention de messe",
    )
    def post(self, request, intention_id: int):
        if getattr(request.user, "pastoral_role", None) not in CLERGY_ROLES:
            return Response(
                {"detail": "Accès réservé au clergé."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            intention = mass_intention_get(intention_id=intention_id)
            intention = mass_intention_accept(intention=intention, pretre=request.user)
        except ApplicationError as e:
            return _error(e)
        return Response(MassIntentionOutputSerializer(intention).data)


class MassIntentionProposeDateApi(ApiAuthMixin, APIView):
    @extend_schema(
        request=MassIntentionProposeDateInputSerializer,
        responses={200: MassIntentionOutputSerializer},
        tags=["mass-intentions"],
        summary="Proposer une date de célébration",
    )
    def post(self, request, intention_id: int):
        if getattr(request.user, "pastoral_role", None) not in CLERGY_ROLES:
            return Response(
                {"detail": "Accès réservé au clergé."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = MassIntentionProposeDateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            intention = mass_intention_get(intention_id=intention_id)
            intention = mass_intention_propose_date(
                intention=intention,
                proposed_date=serializer.validated_data["proposed_date"],
            )
        except ApplicationError as e:
            return _error(e)
        return Response(MassIntentionOutputSerializer(intention).data)


class MassIntentionCelebrateApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: MassIntentionOutputSerializer},
        tags=["mass-intentions"],
        summary="Marquer une intention comme célébrée",
    )
    def post(self, request, intention_id: int):
        if getattr(request.user, "pastoral_role", None) not in CLERGY_ROLES:
            return Response(
                {"detail": "Accès réservé au clergé."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            intention = mass_intention_get(intention_id=intention_id)
            intention = mass_intention_celebrate(intention=intention)
        except ApplicationError as e:
            return _error(e)
        return Response(MassIntentionOutputSerializer(intention).data)


class MassIntentionDeclineApi(ApiAuthMixin, APIView):
    @extend_schema(
        request=MassIntentionDeclineInputSerializer,
        responses={200: MassIntentionOutputSerializer},
        tags=["mass-intentions"],
        summary="Refuser une intention de messe",
    )
    def post(self, request, intention_id: int):
        if getattr(request.user, "pastoral_role", None) not in CLERGY_ROLES:
            return Response(
                {"detail": "Accès réservé au clergé."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = MassIntentionDeclineInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            intention = mass_intention_get(intention_id=intention_id)
            intention = mass_intention_decline(
                intention=intention,
                notes=serializer.validated_data.get("notes", ""),
            )
        except ApplicationError as e:
            return _error(e)
        return Response(MassIntentionOutputSerializer(intention).data)

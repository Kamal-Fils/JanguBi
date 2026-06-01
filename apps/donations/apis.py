from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.openapi import OpenApiTypes
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.mixins import ApiAuthMixin
from apps.api.pagination import LimitOffsetPagination, get_paginated_response
from apps.core.exceptions import ApplicationError
from apps.users.permissions import IsOnboardingCompleted
from apps.users.scoping import user_can_admin_parish

from .selectors import campaign_list_active, donation_list_for_donor
from .serializers import (
    CampaignCreateInputSerializer,
    CampaignOutputSerializer,
    DonationMakeInputSerializer,
    DonationOutputSerializer,
)
from .services import campaign_create, donation_make


def _error(exc: ApplicationError) -> Response:
    return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)


class CampaignListCreateApi(ApiAuthMixin, APIView):
    @extend_schema(
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT),
            OpenApiParameter("offset", OpenApiTypes.INT),
        ],
        responses={200: CampaignOutputSerializer(many=True)},
        tags=["donations"],
        summary="Lister les campagnes actives",
    )
    def get(self, request):
        campaigns = campaign_list_active()
        return get_paginated_response(
            pagination_class=LimitOffsetPagination,
            serializer_class=CampaignOutputSerializer,
            queryset=campaigns,
            request=request,
            view=self,
        )

    @extend_schema(
        request=CampaignCreateInputSerializer,
        responses={201: CampaignOutputSerializer},
        tags=["donations"],
        summary="Créer une campagne de dons (clergé)",
    )
    def post(self, request):
        serializer = CampaignCreateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        # Cloisonnement territorial : une campagne paroissiale exige l'autorité sur la paroisse.
        parish_id = data.get("parish_id")
        if parish_id and not user_can_admin_parish(request.user, parish_id):
            return Response(
                {"detail": "Vous ne pouvez créer une campagne que pour votre paroisse."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            campaign = campaign_create(created_by=request.user, **data)
        except ApplicationError as e:
            return _error(e)
        return Response(CampaignOutputSerializer(campaign).data, status=status.HTTP_201_CREATED)


class DonationMakeApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsOnboardingCompleted]  # A1 — écriture territoriale

    @extend_schema(
        request=DonationMakeInputSerializer,
        responses={201: DonationOutputSerializer},
        tags=["donations"],
        summary="Faire un don",
    )
    def post(self, request):
        serializer = DonationMakeInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            donation = donation_make(donor=request.user, **serializer.validated_data)
        except ApplicationError as e:
            return _error(e)
        return Response(DonationOutputSerializer(donation).data, status=status.HTTP_201_CREATED)


class DonationMyListApi(ApiAuthMixin, APIView):
    @extend_schema(
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT),
            OpenApiParameter("offset", OpenApiTypes.INT),
        ],
        responses={200: DonationOutputSerializer(many=True)},
        tags=["donations"],
        summary="Mes dons",
    )
    def get(self, request):
        donations = donation_list_for_donor(donor=request.user)
        return get_paginated_response(
            pagination_class=LimitOffsetPagination,
            serializer_class=DonationOutputSerializer,
            queryset=donations,
            request=request,
            view=self,
        )

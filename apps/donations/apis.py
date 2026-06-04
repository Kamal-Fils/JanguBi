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

from .models import Donation
from .selectors import campaign_list_active, donation_list_for_donor
from .serializers import (
    CampaignCreateInputSerializer,
    CampaignOutputSerializer,
    DonationConfirmInputSerializer,
    DonationMakeInputSerializer,
    DonationOutputSerializer,
)
from .services import campaign_create, donation_confirm, donation_make


def _error(exc: ApplicationError) -> Response:
    return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)


def _effective_campaign_parish_id(data) -> int | None:
    """Paroisse RÉELLEMENT ciblée par une campagne, quelle que soit la voie
    d'entrée — empêche le contournement du contrôle d'autorité :
    church_id → paroisse de l'église ; sinon parish_id ; sinon scope parish.
    """
    church_id = data.get("church_id")
    if church_id:
        from apps.org.models import Church

        return (
            Church.objects.filter(id=church_id)
            .values_list("parish_id", flat=True)
            .first()
        )
    parish_id = data.get("parish_id")
    if parish_id:
        return parish_id
    if data.get("scope_type") == "parish" and data.get("scope_id"):
        return data["scope_id"]
    return None


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
        # Cloisonnement territorial : autorité requise sur la paroisse EFFECTIVE,
        # résolue après church_id ET scope_type/scope_id (pas seulement parish_id),
        # sinon contournement du garde.
        effective_parish_id = _effective_campaign_parish_id(data)
        if effective_parish_id is not None and not user_can_admin_parish(
            request.user, effective_parish_id
        ):
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


class DonationConfirmApi(ApiAuthMixin, APIView):
    @extend_schema(
        request=DonationConfirmInputSerializer,
        responses={200: DonationOutputSerializer},
        tags=["donations"],
        summary="Confirmer manuellement un don en espèces (autorité paroisse)",
    )
    def post(self, request, donation_id: int):
        donation = (
            Donation.objects.select_related("parish").filter(id=donation_id).first()
        )
        if donation is None:
            return Response(
                {"detail": "Don introuvable."}, status=status.HTTP_404_NOT_FOUND
            )
        # Autorité territoriale RÉELLE sur la paroisse bénéficiaire (sinon 403).
        from apps.users.scoping import is_global_admin

        if not (
            is_global_admin(request.user)
            or (
                donation.parish_id is not None
                and user_can_admin_parish(request.user, donation.parish_id)
            )
        ):
            return Response(
                {"detail": "Vous n'avez pas autorité sur la paroisse de ce don."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = DonationConfirmInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            donation = donation_confirm(donation=donation, **serializer.validated_data)
        except ApplicationError as e:
            return _error(e)
        return Response(DonationOutputSerializer(donation).data)


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

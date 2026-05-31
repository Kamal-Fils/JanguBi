from drf_spectacular.openapi import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.mixins import ApiAuthMixin
from apps.dashboards.selectors import (
    cure_dashboard,
    diocese_dashboard,
    fidele_dashboard,
    user_principal_diocese_id,
    user_principal_parish_id,
)
from apps.users.scoping import user_can_admin_diocese, user_can_admin_parish


class FideleDashboardApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: OpenApiTypes.OBJECT},
        tags=["dashboards"],
        summary="Tableau de bord du fidèle (vue personnelle)",
    )
    def get(self, request):
        return Response(fidele_dashboard(user=request.user))


class MyParishDashboardApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: OpenApiTypes.OBJECT},
        tags=["dashboards"],
        summary="Tableau de bord de ma paroisse (curé connecté)",
    )
    def get(self, request):
        parish_id = user_principal_parish_id(user=request.user)
        if not parish_id:
            return Response(
                {"detail": "Aucune paroisse rattachée à votre compte."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(cure_dashboard(parish_id=parish_id))


class ParishDashboardApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: OpenApiTypes.OBJECT},
        tags=["dashboards"],
        summary="Tableau de bord d'une paroisse (total fidèles, flux de dons, files)",
    )
    def get(self, request, parish_id: int):
        if not user_can_admin_parish(request.user, parish_id):
            return Response(
                {"detail": "Accès réservé à l'administrateur de la paroisse."},
                status=status.HTTP_403_FORBIDDEN,
            )
        data = cure_dashboard(parish_id=parish_id)
        if data is None:
            return Response({"detail": "Paroisse introuvable."}, status=status.HTTP_404_NOT_FOUND)
        return Response(data)


class MyDioceseDashboardApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: OpenApiTypes.OBJECT},
        tags=["dashboards"],
        summary="Tableau de bord de mon diocèse (évêque connecté)",
    )
    def get(self, request):
        diocese_id = user_principal_diocese_id(user=request.user)
        if not diocese_id:
            return Response(
                {"detail": "Aucun diocèse rattaché à votre compte."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(diocese_dashboard(diocese_id=diocese_id))


class DioceseDashboardApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: OpenApiTypes.OBJECT},
        tags=["dashboards"],
        summary="Tableau de bord diocésain (évêque)",
    )
    def get(self, request, diocese_id: int):
        if not user_can_admin_diocese(request.user, diocese_id):
            return Response(
                {"detail": "Accès réservé à l'administrateur du diocèse."},
                status=status.HTTP_403_FORBIDDEN,
            )
        data = diocese_dashboard(diocese_id=diocese_id)
        if data is None:
            return Response({"detail": "Diocèse introuvable."}, status=status.HTTP_404_NOT_FOUND)
        return Response(data)

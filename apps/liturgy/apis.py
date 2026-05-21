import datetime

from asgiref.sync import async_to_sync
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from drf_spectacular.utils import OpenApiParameter, extend_schema
from drf_spectacular.openapi import OpenApiTypes
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.mixins import ApiAuthMixin
from apps.liturgy.models import AelfResource, LiturgicalDate, Office, Reading
from apps.liturgy.serializers import (
    AelfResourceSerializer,
    LiturgicalDateSerializer,
    OfficeSerializer,
    ReadingSerializer,
)
from apps.liturgy.services import AelfService

CLERGY_ROLES = {"religieux", "diacre", "pretre", "eveque", "archeveque"}


class CanAccessLiturgyOfHours(IsAuthenticated):
    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        role = getattr(request.user, "role", None)
        pastoral = getattr(request.user, "pastoral_role", None)
        return role in CLERGY_ROLES or (pastoral is not None and pastoral in CLERGY_ROLES)


# ---------------------------------------------------------------------------
# Base helpers
# ---------------------------------------------------------------------------

class _DailyLiturgyBase(APIView):
    """Common date/zone parsing and AELF auto-sync for liturgy endpoints."""

    permission_classes = [AllowAny]

    def _get_params(self, request):
        date_str = request.query_params.get("date")
        zone = request.query_params.get("zone", "afrique")
        if not date_str:
            date_str = timezone.localtime().date().isoformat()
        return date_str, zone

    def _ensure_data(self, date_str, zone):
        try:
            target_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return None, False

        exists = LiturgicalDate.objects.filter(date=target_date, zone=zone).exists()
        if not exists:
            async_to_sync(AelfService.sync_daily_data)(date_str, zone)

        date_obj = (
            LiturgicalDate.objects.filter(date=target_date, zone=zone)
            .prefetch_related("readings__matched_verses", "offices")
            .first()
        )
        return date_obj, True


class _OfficeBase(_DailyLiturgyBase):
    """Base for the 7 Liturgy of the Hours endpoints (clergy-only)."""

    permission_classes = [CanAccessLiturgyOfHours]
    office_type: str | None = None

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "date",
                OpenApiTypes.STR,
                description="Date YYYY-MM-DD (défaut: aujourd'hui)",
            ),
            OpenApiParameter(
                "zone",
                OpenApiTypes.STR,
                description="Zone liturgique (défaut: afrique)",
            ),
        ],
        responses={200: OfficeSerializer},
        tags=["Liturgy"],
        summary="Office de la Liturgie des Heures (clergé uniquement)",
    )
    def get(self, request):
        if not self.office_type:
            return Response(
                {"detail": "Office type not configured."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        date_str, zone = self._get_params(request)
        date_obj, valid = self._ensure_data(date_str, zone)

        if not valid:
            return Response(
                {"detail": "Format de date invalide. Utilisez YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not date_obj:
            return Response(
                {"detail": "Données liturgiques non disponibles."},
                status=status.HTTP_404_NOT_FOUND,
            )
        office = date_obj.offices.filter(office_type=self.office_type).first()
        if not office:
            return Response(
                {"detail": f"Office '{self.office_type}' non trouvé pour cette date."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(OfficeSerializer(office).data)


# ---------------------------------------------------------------------------
# Public endpoints — informations + messes
# ---------------------------------------------------------------------------

class LiturgyInformationsApi(_DailyLiturgyBase):
    @extend_schema(
        parameters=[
            OpenApiParameter("date", OpenApiTypes.STR, description="Date YYYY-MM-DD"),
            OpenApiParameter("zone", OpenApiTypes.STR, description="Zone liturgique"),
        ],
        responses={200: LiturgicalDateSerializer},
        tags=["Liturgy"],
        summary="Informations sur la date liturgique",
    )
    def get(self, request):
        date_str, zone = self._get_params(request)
        date_obj, valid = self._ensure_data(date_str, zone)
        if not valid:
            return Response(
                {"detail": "Format de date invalide."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not date_obj:
            return Response({"detail": "Données non disponibles."}, status=status.HTTP_404_NOT_FOUND)
        return Response(LiturgicalDateSerializer(date_obj).data)


class LiturgyMessesApi(_DailyLiturgyBase):
    @extend_schema(
        parameters=[
            OpenApiParameter("date", OpenApiTypes.STR, description="Date YYYY-MM-DD"),
            OpenApiParameter("zone", OpenApiTypes.STR, description="Zone liturgique"),
        ],
        responses={200: ReadingSerializer(many=True)},
        tags=["Liturgy"],
        summary="Lectures de la Messe du jour",
    )
    def get(self, request):
        date_str, zone = self._get_params(request)
        date_obj, valid = self._ensure_data(date_str, zone)
        if not valid:
            return Response(
                {"detail": "Format de date invalide."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not date_obj:
            return Response({"detail": "Données non disponibles."}, status=status.HTTP_404_NOT_FOUND)
        return Response(ReadingSerializer(date_obj.readings.all(), many=True).data)


class LiturgyTodayApi(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        responses={200: LiturgicalDateSerializer},
        tags=["Liturgy"],
        summary="Liturgie du jour complet (messe + offices)",
    )
    @method_decorator(cache_page(60 * 60 * 1))
    def get(self, request):
        today = timezone.localtime().date()
        date_obj = (
            LiturgicalDate.objects.filter(date=today, zone="afrique")
            .prefetch_related("readings__matched_verses", "offices")
            .first()
        )
        if not date_obj:
            async_to_sync(AelfService.sync_daily_data)(today.isoformat(), "afrique")
            date_obj = (
                LiturgicalDate.objects.filter(date=today, zone="afrique")
                .prefetch_related("readings__matched_verses", "offices")
                .first()
            )
        if not date_obj:
            return Response(
                {"detail": "Données liturgiques du jour non encore synchronisées."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(LiturgicalDateSerializer(date_obj).data)


class LiturgyDateApi(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        responses={200: LiturgicalDateSerializer},
        tags=["Liturgy"],
        summary="Liturgie pour une date spécifique",
    )
    def get(self, request, date_str):
        from django.core.cache import cache

        cache_key = f"liturgy_date_api_v2_{date_str}"
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)

        try:
            target_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return Response(
                {"detail": "Format de date invalide. Utilisez YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        date_obj = (
            LiturgicalDate.objects.filter(date=target_date, zone="afrique")
            .prefetch_related("readings__matched_verses", "offices")
            .first()
        )
        if not date_obj:
            async_to_sync(AelfService.sync_daily_data)(date_str, "afrique")
            date_obj = (
                LiturgicalDate.objects.filter(date=target_date, zone="afrique")
                .prefetch_related("readings__matched_verses", "offices")
                .first()
            )
        if not date_obj:
            return Response(
                {"detail": f"Données liturgiques pour {date_str} introuvables."},
                status=status.HTTP_404_NOT_FOUND,
            )

        data = LiturgicalDateSerializer(date_obj).data
        cache.set(cache_key, data, timeout=60 * 60 * 24)
        return Response(data)


class ReadingDetailApi(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        responses={200: ReadingSerializer},
        tags=["Liturgy"],
        summary="Détail d'une lecture de messe",
    )
    @method_decorator(cache_page(60 * 60 * 24))
    def get(self, request, pk):
        try:
            reading = Reading.objects.prefetch_related("matched_verses").get(pk=pk)
        except Reading.DoesNotExist:
            return Response({"detail": "Lecture introuvable."}, status=status.HTTP_404_NOT_FOUND)
        return Response(ReadingSerializer(reading).data)


class OfficeDetailApi(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        responses={200: OfficeSerializer},
        tags=["Liturgy"],
        summary="Détail d'un office liturgique",
    )
    @method_decorator(cache_page(60 * 60 * 24))
    def get(self, request, pk):
        try:
            office = Office.objects.get(pk=pk)
        except Office.DoesNotExist:
            return Response({"detail": "Office introuvable."}, status=status.HTTP_404_NOT_FOUND)
        return Response(OfficeSerializer(office).data)


# ---------------------------------------------------------------------------
# Liturgy of the Hours — clergy-only (7 offices)
# ---------------------------------------------------------------------------

class LiturgyLaudesApi(_OfficeBase):
    office_type = "laudes"


class LiturgyTierceApi(_OfficeBase):
    office_type = "tierce"


class LiturgySexteApi(_OfficeBase):
    office_type = "sexte"


class LiturgyNoneApi(_OfficeBase):
    office_type = "none"


class LiturgyVepresApi(_OfficeBase):
    office_type = "vepres"


class LiturgyCompliesApi(_OfficeBase):
    office_type = "complies"


class LiturgyLecturesApi(_OfficeBase):
    office_type = "lectures"

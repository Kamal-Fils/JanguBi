import datetime

from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from drf_spectacular.openapi import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.mixins import ApiAuthMixin
from apps.liturgy.models import LiturgicalDate, Office, Reading
from apps.liturgy.serializers import (
    LiturgicalDateSerializer,
    OfficeSerializer,
    ReadingSerializer,
)
from apps.liturgy.services import AelfService

CLERGY_ROLES = {"religieux", "diacre", "pretre", "eveque", "archeveque"}


def user_can_access_hours(user) -> bool:
    """La Liturgie des Heures est réservée au clergé/religieux (SRS §16)."""
    role = getattr(user, "role", None)
    pastoral = getattr(user, "pastoral_role", None)
    return role in CLERGY_ROLES or (pastoral is not None and pastoral in CLERGY_ROLES)


class CanAccessLiturgyOfHours(IsAuthenticated):
    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        return user_can_access_hours(request.user)


# ---------------------------------------------------------------------------
# Base helpers
# ---------------------------------------------------------------------------

class _DailyLiturgyBase(ApiAuthMixin, APIView):
    """
    Common date/zone parsing and AELF auto-sync for liturgy endpoints.

    ApiAuthMixin est INDISPENSABLE : sans lui, le Bearer JWT n'était pas lu
    (pas de JWTAuthentication) et les endpoints clergé renvoyaient 401 à tout
    client SPA/mobile authentifié. Les vues publiques gardent AllowAny.
    """

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


def _strip_offices_if_not_clergy(data: dict, user) -> dict:
    """
    Le payload complet (cache partagé) contient messe + offices ; les offices
    (Liturgie des Heures) sont réservés au clergé/religieux. Copie sans
    mutation de l'entrée en cache.
    """
    if user_can_access_hours(user):
        return data
    return {**data, "offices": []}


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


class LiturgyTodayApi(ApiAuthMixin, APIView):
    # Jour liturgique complet : les LECTURES DE MESSE sont pour tout utilisateur
    # connecté (c'est l'onglet « Aujourd'hui » du fidèle) ; seuls les OFFICES
    # relèvent de la Liturgie des Heures (clergé/religieux) et sont retirés du
    # payload pour les autres. NB : l'ancien gate clergé sur tout l'endpoint ne
    # « marchait » pour les fidèles que par une fuite de @cache_page.
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: LiturgicalDateSerializer},
        tags=["Liturgy"],
        summary="Liturgie du jour complet (lectures pour tous, offices clergé)",
    )
    def get(self, request):
        # Cache manuel APRÈS la permission (l'ancien @cache_page servait la même
        # entrée à tous — y compris des réponses d'erreur mises en cache — sans
        # re-passer par le gate clergé).
        today = timezone.localtime().date()
        cache_key = f"liturgy_today_api_{today.isoformat()}"
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(_strip_offices_if_not_clergy(cached_data, request.user))

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
        data = LiturgicalDateSerializer(date_obj).data
        cache.set(cache_key, data, timeout=60 * 60)
        return Response(_strip_offices_if_not_clergy(data, request.user))


class LiturgyDateApi(ApiAuthMixin, APIView):
    # Même contrat que /today/ : lectures de messe pour tout utilisateur
    # connecté, offices réservés au clergé (strippés du payload sinon).
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: LiturgicalDateSerializer},
        tags=["Liturgy"],
        summary="Liturgie pour une date (lectures pour tous, offices clergé)",
    )
    def get(self, request, date_str):
        cache_key = f"liturgy_date_api_v2_{date_str}"
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(_strip_offices_if_not_clergy(cached_data, request.user))

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
        return Response(_strip_offices_if_not_clergy(data, request.user))


class ReadingDetailApi(ApiAuthMixin, APIView):
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


class OfficeDetailApi(ApiAuthMixin, APIView):
    # Un office isolé = Liturgie des Heures → réservé au clergé/religieux, comme
    # les endpoints /v1/<office>/. Évite le contournement du gate par pk direct.
    permission_classes = [CanAccessLiturgyOfHours]

    @extend_schema(
        responses={200: OfficeSerializer},
        tags=["Liturgy"],
        summary="Détail d'un office liturgique (clergé uniquement)",
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

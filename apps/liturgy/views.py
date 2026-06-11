import datetime

from asgiref.sync import sync_to_async
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.liturgy.models import LiturgicalDate, Office, Reading
from apps.liturgy.serializers import (
    LiturgicalDateSerializer,
    OfficeSerializer,
    ReadingSerializer,
)
from apps.liturgy.services import AelfService


class DailyLiturgyBaseApi(APIView):
    """
    Base API view for Daily Liturgy endpoints.
    Provides common logic for date/zone parsing and automatic synchronization.
    """
    permission_classes = [AllowAny]

    def get_params(self, request):
        date_str = request.query_params.get("date")
        zone = request.query_params.get("zone", "afrique")
        
        if not date_str:
            date_str = timezone.localtime().date().isoformat()
            
        return date_str, zone

    async def ensure_data(self, date_str, zone):
        """Checks if data exists, otherwise syncs from AELF."""
        try:
            target_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return None, False

        exists = await sync_to_async(LiturgicalDate.objects.filter(date=target_date, zone=zone).exists)()
        
        if not exists:
            # Sync data from AELF
            await AelfService.sync_daily_data(date_str, zone)
            
        date_obj = await sync_to_async(lambda: LiturgicalDate.objects.filter(date=target_date, zone=zone).prefetch_related(
            "readings__matched_verses", "offices"
        ).first())()
        
        return date_obj, True


class LiturgyInformationsApi(DailyLiturgyBaseApi):
    @extend_schema(
        parameters=[
            OpenApiParameter("date", OpenApiTypes.STR, description="Date in YYYY-MM-DD format (default: today)"),
            OpenApiParameter("zone", OpenApiTypes.STR, description="Liturgical zone (default: romain)"),
        ],
        responses=LiturgicalDateSerializer,
        tags=["Liturgy V1"],
        summary="Informations about the specified date and zone.",
    )
    def get(self, request):
        date_str, zone = self.get_params(request)
        from asgiref.sync import async_to_sync
        
        date_obj, valid_date = async_to_sync(self.ensure_data)(date_str, zone)
        
        if not valid_date:
            return Response({"error": "Invalid date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
            
        if not date_obj:
            return Response({"error": "Data not available."}, status=status.HTTP_404_NOT_FOUND)
            
        serializer = LiturgicalDateSerializer(date_obj)
        return Response(serializer.data)


class LiturgyMessesApi(DailyLiturgyBaseApi):
    @extend_schema(
        parameters=[
            OpenApiParameter("date", OpenApiTypes.STR, description="Date in YYYY-MM-DD format (default: today)"),
            OpenApiParameter("zone", OpenApiTypes.STR, description="Liturgical zone (default: romain)"),
        ],
        responses=ReadingSerializer(many=True),
        tags=["Liturgy V1"],
        summary="Mass(es) for the specified date and zone.",
    )
    def get(self, request):
        date_str, zone = self.get_params(request)
        from asgiref.sync import async_to_sync
        
        date_obj, valid_date = async_to_sync(self.ensure_data)(date_str, zone)
        
        if not valid_date:
            return Response({"error": "Invalid date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
            
        if not date_obj:
            return Response({"error": "Data not available."}, status=status.HTTP_404_NOT_FOUND)
            
        serializer = ReadingSerializer(date_obj.readings.all(), many=True)
        return Response(serializer.data)


class LiturgyOfficeApi(DailyLiturgyBaseApi):
    office_type = None

    @extend_schema(
        parameters=[
            OpenApiParameter("date", OpenApiTypes.STR, description="Date in YYYY-MM-DD format (default: today)"),
            OpenApiParameter("zone", OpenApiTypes.STR, description="Liturgical zone (default: romain)"),
        ],
        responses=OfficeSerializer,
        tags=["Liturgy V1"],
        summary="Office for the specified date and zone.",
    )
    def get(self, request):
        if not self.office_type:
            return Response({"error": "Office type not configured."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
        date_str, zone = self.get_params(request)
        from asgiref.sync import async_to_sync
        
        date_obj, valid_date = async_to_sync(self.ensure_data)(date_str, zone)
        
        if not valid_date:
            return Response({"error": "Invalid date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
            
        if not date_obj:
            return Response({"error": "Data not available."}, status=status.HTTP_404_NOT_FOUND)
            
        office = date_obj.offices.filter(office_type=self.office_type).first()
        if not office:
             return Response({"error": f"Office {self.office_type} not found for this date."}, status=status.HTTP_404_NOT_FOUND)
             
        serializer = OfficeSerializer(office)
        return Response(serializer.data)


class LiturgyLaudesApi(LiturgyOfficeApi):
    office_type = "laudes"

class LiturgyTierceApi(LiturgyOfficeApi):
    office_type = "tierce"

class LiturgySexteApi(LiturgyOfficeApi):
    office_type = "sexte"

class LiturgyNoneApi(LiturgyOfficeApi):
    office_type = "none"

class LiturgyVepresApi(LiturgyOfficeApi):
    office_type = "vepres"

class LiturgyCompliesApi(LiturgyOfficeApi):
    office_type = "complies"

class LiturgyLecturesApi(LiturgyOfficeApi):
    office_type = "lectures"


class LiturgyTodayApi(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        responses=LiturgicalDateSerializer, 
        tags=["Liturgy"], 
        summary="Get today's Liturgical data (Mass Readings, Offices)",
        description="""
        Retrieve the official liturgical texts for the CURRENT day (in the 'romain' zone).
        This includes the 'Mass' readings (First Reading, Gospel, etc.) and the 
        Liturgy of the Hours text blocks (Lauds, Vespers, Compline, etc.).
        """
    )
    @method_decorator(cache_page(60 * 60 * 1))
    def get(self, request):
        today = timezone.localtime().date()
        date_obj = LiturgicalDate.objects.filter(date=today, zone="afrique").prefetch_related(
            "readings__matched_verses", "offices"
        ).first()

        if not date_obj:
            from asgiref.sync import async_to_sync
            async_to_sync(AelfService.sync_daily_data)(today.isoformat(), "afrique")
            date_obj = LiturgicalDate.objects.filter(date=today, zone="afrique").prefetch_related(
                "readings__matched_verses", "offices"
            ).first()

        if not date_obj:
            return Response(
                {"error": "Liturgy data for today has not been synchronized yet."}, 
                status=status.HTTP_404_NOT_FOUND
            )

        # Flag for serializer caching
        date_obj._prefetched_objects_cache = date_obj._prefetched_objects_cache or {}
        date_obj._prefetched_objects_cache["readings"] = date_obj.readings.all()
        date_obj._prefetched_objects_cache["offices"] = date_obj.offices.all()

        serializer = LiturgicalDateSerializer(date_obj)
        return Response(serializer.data)


class LiturgyDateApi(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        responses=LiturgicalDateSerializer, 
        tags=["Liturgy"], 
        summary="Get Liturgical data for a specific date",
        description="""
        Retrieve the liturgical texts for a specific date (YYYY-MM-DD).
        If the data is not available locally, it syncs from AELF.
        """
    )
    def get(self, request, date_str):
        from django.core.cache import cache
        
        # 1. Vérifie le cache MANUELLEMENT pour éviter les 404 indésirables
        cache_key = f"liturgy_date_api_v2_{date_str}"
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)

        try:
            target_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return Response({"error": "Invalid date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        date_obj = LiturgicalDate.objects.filter(date=target_date, zone="afrique").prefetch_related(
            "readings__matched_verses", "offices"
        ).first()

        if not date_obj:
            from asgiref.sync import async_to_sync
            async_to_sync(AelfService.sync_daily_data)(date_str, "afrique")
            date_obj = LiturgicalDate.objects.filter(date=target_date, zone="afrique").prefetch_related(
                "readings__matched_verses", "offices"
            ).first()

        if not date_obj:
            return Response(
                {"error": f"Liturgy data for {date_str} not found."}, 
                status=status.HTTP_404_NOT_FOUND
            )

        date_obj._prefetched_objects_cache = date_obj._prefetched_objects_cache or {}
        date_obj._prefetched_objects_cache["readings"] = date_obj.readings.all()
        date_obj._prefetched_objects_cache["offices"] = date_obj.offices.all()

        serializer = LiturgicalDateSerializer(date_obj)
        
        # 3. Ce n'est qu'en cas de SUCCÈS 200 qu'on gèle le résultat pour 24h
        cache.set(cache_key, serializer.data, timeout=60 * 60 * 24)
        
        return Response(serializer.data)


class ReadingDetailApi(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        responses=ReadingSerializer, 
        tags=["Liturgy"], 
        summary="Get details of a specific Mass Reading",
        description="""
        Retrieve a specific Reading (e.g., the Gospel) by its ID.
        This includes any matched local Bible verses (cross-references).
        """
    )
    @method_decorator(cache_page(60 * 60 * 24))
    def get(self, request, pk):
        try:
            reading = Reading.objects.prefetch_related("matched_verses").get(pk=pk)
            serializer = ReadingSerializer(reading)
            return Response(serializer.data)
        except Reading.DoesNotExist:
            return Response({"error": "Reading not found."}, status=status.HTTP_404_NOT_FOUND)


class OfficeDetailApi(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        responses=OfficeSerializer, 
        tags=["Liturgy"], 
        summary="Get details of a specific Office (e.g., Lauds)",
        description="""
        Retrieve a specific Office by its ID. 
        Returns the hymns, psalms, and intercessions associated with that office.
        """
    )
    @method_decorator(cache_page(60 * 60 * 24))
    def get(self, request, pk):
        try:
            office = Office.objects.get(pk=pk)
            serializer = OfficeSerializer(office)
            return Response(serializer.data)
        except Office.DoesNotExist:
            return Response({"error": "Office not found."}, status=status.HTTP_404_NOT_FOUND)
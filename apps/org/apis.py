from drf_spectacular.utils import OpenApiParameter, extend_schema
from drf_spectacular.openapi import OpenApiTypes
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.mixins import ApiAuthMixin
from apps.api.pagination import LimitOffsetPagination, get_paginated_response
from apps.core.exceptions import ApplicationError
from apps.org.selectors import diocese_list, parish_list, parish_get_by_id, province_list
from apps.org.serializers import (
    DioceseCreateInputSerializer,
    DioceseOutputSerializer,
    ParishCreateInputSerializer,
    ParishOutputSerializer,
    ProvinceCreateInputSerializer,
    ProvinceOutputSerializer,
)
from apps.org.services import diocese_create, parish_create, province_create
from apps.users.permissions import IsSuperAdmin


def _error(exc: ApplicationError) -> Response:
    return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Provinces
# ---------------------------------------------------------------------------

class ProvinceListApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: ProvinceOutputSerializer(many=True)},
        tags=["org"],
        summary="Lister les provinces",
    )
    def get(self, request):
        provinces = province_list()
        return Response(ProvinceOutputSerializer(provinces, many=True).data)

    @extend_schema(
        request=ProvinceCreateInputSerializer,
        responses={201: ProvinceOutputSerializer},
        tags=["org"],
        summary="Créer une province (super_admin)",
    )
    def post(self, request):
        self.check_permissions(request)
        if not IsSuperAdmin().has_permission(request, self):
            return Response({"detail": "Accès réservé au Super Admin."}, status=status.HTTP_403_FORBIDDEN)
        serializer = ProvinceCreateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            province = province_create(**serializer.validated_data)
        except ApplicationError as e:
            return _error(e)
        return Response(ProvinceOutputSerializer(province).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Diocèses
# ---------------------------------------------------------------------------

class DioceseListApi(ApiAuthMixin, APIView):
    @extend_schema(
        parameters=[
            OpenApiParameter("province", OpenApiTypes.INT, description="Filtrer par province ID"),
        ],
        responses={200: DioceseOutputSerializer(many=True)},
        tags=["org"],
        summary="Lister les diocèses",
    )
    def get(self, request):
        province_id = request.query_params.get("province")
        dioceses = diocese_list(province_id=int(province_id) if province_id else None)
        return Response(DioceseOutputSerializer(dioceses, many=True).data)

    @extend_schema(
        request=DioceseCreateInputSerializer,
        responses={201: DioceseOutputSerializer},
        tags=["org"],
        summary="Créer un diocèse (super_admin)",
    )
    def post(self, request):
        if not IsSuperAdmin().has_permission(request, self):
            return Response({"detail": "Accès réservé au Super Admin."}, status=status.HTTP_403_FORBIDDEN)
        serializer = DioceseCreateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        from apps.org.models import Province
        from apps.core.exceptions import ApplicationError as AE
        try:
            province = Province.objects.get(id=data["province_id"])
        except Province.DoesNotExist:
            return Response({"detail": "Province introuvable."}, status=status.HTTP_404_NOT_FOUND)
        try:
            diocese = diocese_create(name=data["name"], code=data["code"], province=province)
        except AE as e:
            return _error(e)
        return Response(DioceseOutputSerializer(diocese).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Paroisses
# ---------------------------------------------------------------------------

class ParishListApi(ApiAuthMixin, APIView):
    class Pagination(LimitOffsetPagination):
        default_limit = 50
        max_limit = 200

    @extend_schema(
        parameters=[
            OpenApiParameter("diocese", OpenApiTypes.INT, description="Filtrer par diocèse ID"),
            OpenApiParameter("search", OpenApiTypes.STR, description="Recherche par nom ou ville"),
            OpenApiParameter("limit", OpenApiTypes.INT, description="Nombre de résultats"),
            OpenApiParameter("offset", OpenApiTypes.INT, description="Offset de pagination"),
        ],
        responses={200: ParishOutputSerializer(many=True)},
        tags=["org"],
        summary="Lister les paroisses avec recherche et pagination",
    )
    def get(self, request):
        diocese_id = request.query_params.get("diocese")
        search = request.query_params.get("search")
        parishes = parish_list(
            diocese_id=int(diocese_id) if diocese_id else None,
            search=search or None,
        )
        return get_paginated_response(
            pagination_class=self.Pagination,
            serializer_class=ParishOutputSerializer,
            queryset=parishes,
            request=request,
            view=self,
        )

    @extend_schema(
        request=ParishCreateInputSerializer,
        responses={201: ParishOutputSerializer},
        tags=["org"],
        summary="Créer une paroisse (super_admin)",
    )
    def post(self, request):
        if not IsSuperAdmin().has_permission(request, self):
            return Response({"detail": "Accès réservé au Super Admin."}, status=status.HTTP_403_FORBIDDEN)
        serializer = ParishCreateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        from apps.org.models import Diocese
        try:
            diocese = Diocese.objects.get(id=data["diocese_id"])
        except Diocese.DoesNotExist:
            return Response({"detail": "Diocèse introuvable."}, status=status.HTTP_404_NOT_FOUND)
        try:
            parish = parish_create(
                name=data["name"],
                diocese=diocese,
                city=data.get("city", ""),
                address=data.get("address", ""),
            )
        except ApplicationError as e:
            return _error(e)
        return Response(ParishOutputSerializer(parish).data, status=status.HTTP_201_CREATED)


class ParishDetailApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: ParishOutputSerializer},
        tags=["org"],
        summary="Détail d'une paroisse",
    )
    def get(self, request, parish_id: int):
        try:
            parish = parish_get_by_id(parish_id=parish_id)
        except ApplicationError as e:
            return Response({"detail": e.message}, status=status.HTTP_404_NOT_FOUND)
        return Response(ParishOutputSerializer(parish).data)

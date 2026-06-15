from drf_spectacular.openapi import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.mixins import ApiAuthMixin
from apps.api.pagination import (
    LimitOffsetPagination,
    get_paginated_response,
    paginated_response_serializer,
)
from apps.core.exceptions import ApplicationError
from apps.org.selectors import (
    church_get_by_id,
    church_list,
    deanery_list,
    diocese_list,
    parish_get_by_id,
    parish_list,
    province_list,
)
from apps.org.serializers import (
    ChurchCreateInputSerializer,
    ChurchOutputSerializer,
    DeaneryCreateInputSerializer,
    DeaneryOutputSerializer,
    DioceseCreateInputSerializer,
    DioceseOutputSerializer,
    ParishCreateInputSerializer,
    ParishOutputSerializer,
    ParishUpdateInputSerializer,
    ProvinceCreateInputSerializer,
    ProvinceOutputSerializer,
)
from apps.org.services import (
    church_create,
    deanery_create,
    diocese_create,
    parish_create,
    parish_delete,
    parish_update,
    province_create,
)
from apps.users.permissions import IsSuperAdmin
from apps.users.scoping import user_can_admin_diocese, user_can_admin_parish


def _error(exc: ApplicationError) -> Response:
    return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Provinces
# ---------------------------------------------------------------------------

class ProvinceListApi(ApiAuthMixin, APIView):
    class Pagination(LimitOffsetPagination):
        default_limit = 100
        max_limit = 200

    @extend_schema(
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT, description="Nombre de résultats"),
            OpenApiParameter("offset", OpenApiTypes.INT, description="Offset de pagination"),
        ],
        responses={200: paginated_response_serializer(ProvinceOutputSerializer)},
        tags=["org"],
        summary="Lister les provinces",
    )
    def get(self, request):
        provinces = province_list()
        # Enveloppe paginée {count, results} — cohérence dioceses/parishes/churches ;
        # le front (get-provinces.ts) déballe `.results` (BUG-B3 : liste nue → Zod throw).
        return get_paginated_response(
            pagination_class=self.Pagination,
            serializer_class=ProvinceOutputSerializer,
            queryset=provinces,
            request=request,
            view=self,
        )

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
    class Pagination(LimitOffsetPagination):
        default_limit = 100
        max_limit = 200

    @extend_schema(
        parameters=[
            OpenApiParameter("province", OpenApiTypes.INT, description="Filtrer par province ID"),
            OpenApiParameter("limit", OpenApiTypes.INT, description="Nombre de résultats"),
            OpenApiParameter("offset", OpenApiTypes.INT, description="Offset de pagination"),
        ],
        responses={200: paginated_response_serializer(DioceseOutputSerializer)},
        tags=["org"],
        summary="Lister les diocèses",
    )
    def get(self, request):
        province_id = request.query_params.get("province")
        dioceses = diocese_list(province_id=int(province_id) if province_id else None)
        # Enveloppe paginée {count, results} — cohérence avec ParishListApi ; le
        # front (get-dioceses.ts) déballe `.results`.
        return get_paginated_response(
            pagination_class=self.Pagination,
            serializer_class=DioceseOutputSerializer,
            queryset=dioceses,
            request=request,
            view=self,
        )

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
        from apps.core.exceptions import ApplicationError as AE
        from apps.org.models import Province
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
            OpenApiParameter("city", OpenApiTypes.STR, description="Filtrer par ville (dédié)"),
            OpenApiParameter("limit", OpenApiTypes.INT, description="Nombre de résultats"),
            OpenApiParameter("offset", OpenApiTypes.INT, description="Offset de pagination"),
        ],
        responses={200: paginated_response_serializer(ParishOutputSerializer)},
        tags=["org"],
        summary="Lister/rechercher les paroisses (toutes paroisses) — picker documents",
    )
    def get(self, request):
        diocese_id = request.query_params.get("diocese")
        search = request.query_params.get("search")
        city = request.query_params.get("city")
        parishes = parish_list(
            diocese_id=int(diocese_id) if diocese_id else None,
            search=search or None,
            city=city or None,
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

    @extend_schema(
        request=ParishUpdateInputSerializer,
        responses={200: ParishOutputSerializer},
        tags=["org"],
        summary="Modifier une paroisse (super_admin)",
    )
    def patch(self, request, parish_id: int):
        if not IsSuperAdmin().has_permission(request, self):
            return Response(
                {"detail": "Accès réservé au Super Admin."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            parish = parish_get_by_id(parish_id=parish_id)
        except ApplicationError as e:
            return Response({"detail": e.message}, status=status.HTTP_404_NOT_FOUND)
        serializer = ParishUpdateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            parish = parish_update(parish=parish, **serializer.validated_data)
        except ApplicationError as e:
            return _error(e)
        return Response(ParishOutputSerializer(parish).data)

    @extend_schema(
        responses={204: None},
        tags=["org"],
        summary="Supprimer une paroisse (super_admin)",
    )
    def delete(self, request, parish_id: int):
        if not IsSuperAdmin().has_permission(request, self):
            return Response(
                {"detail": "Accès réservé au Super Admin."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            parish = parish_get_by_id(parish_id=parish_id)
        except ApplicationError as e:
            return Response({"detail": e.message}, status=status.HTTP_404_NOT_FOUND)
        try:
            parish_delete(parish=parish)
        except ApplicationError as e:
            return _error(e)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Églises
# ---------------------------------------------------------------------------

class ChurchListApi(ApiAuthMixin, APIView):
    class Pagination(LimitOffsetPagination):
        default_limit = 100
        max_limit = 200

    @extend_schema(
        parameters=[
            OpenApiParameter("parish", OpenApiTypes.INT, description="Filtrer par paroisse ID"),
            OpenApiParameter("limit", OpenApiTypes.INT, description="Nombre de résultats"),
            OpenApiParameter("offset", OpenApiTypes.INT, description="Offset de pagination"),
        ],
        responses={200: paginated_response_serializer(ChurchOutputSerializer)},
        tags=["org"],
        summary="Lister les églises (filtrable par paroisse)",
    )
    def get(self, request):
        parish_id = request.query_params.get("parish")
        churches = church_list(parish_id=int(parish_id) if parish_id else None)
        # Enveloppe paginée {count, results} — cohérence avec ParishListApi ; le
        # front (get-churches.ts) déballe `.results`.
        return get_paginated_response(
            pagination_class=self.Pagination,
            serializer_class=ChurchOutputSerializer,
            queryset=churches,
            request=request,
            view=self,
        )

    @extend_schema(
        request=ChurchCreateInputSerializer,
        responses={201: ChurchOutputSerializer},
        tags=["org"],
        summary="Créer une église (admin de la paroisse)",
    )
    def post(self, request):
        serializer = ChurchCreateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        from apps.org.models import Parish
        try:
            parish = Parish.objects.get(id=data["parish_id"])
        except Parish.DoesNotExist:
            return Response({"detail": "Paroisse introuvable."}, status=status.HTTP_404_NOT_FOUND)
        if not user_can_admin_parish(request.user, parish.id):
            return Response(
                {"detail": "Accès réservé à l'administrateur de la paroisse."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            church = church_create(
                parish=parish,
                name=data["name"],
                church_type=data["church_type"],
                is_main=data["is_main"],
                city=data.get("city", ""),
                address=data.get("address", ""),
            )
        except ApplicationError as e:
            return _error(e)
        return Response(ChurchOutputSerializer(church).data, status=status.HTTP_201_CREATED)


class ChurchDetailApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: ChurchOutputSerializer},
        tags=["org"],
        summary="Détail d'une église",
    )
    def get(self, request, church_id: int):
        try:
            church = church_get_by_id(church_id=church_id)
        except ApplicationError as e:
            return Response({"detail": e.message}, status=status.HTTP_404_NOT_FOUND)
        return Response(ChurchOutputSerializer(church).data)


# ---------------------------------------------------------------------------
# Doyennés
# ---------------------------------------------------------------------------

class DeaneryListApi(ApiAuthMixin, APIView):
    @extend_schema(
        parameters=[OpenApiParameter("diocese", OpenApiTypes.INT, description="Filtrer par diocèse ID")],
        responses={200: DeaneryOutputSerializer(many=True)},
        tags=["org"],
        summary="Lister les doyennés (filtrable par diocèse)",
    )
    def get(self, request):
        diocese_id = request.query_params.get("diocese")
        deaneries = deanery_list(diocese_id=int(diocese_id) if diocese_id else None)
        return Response(DeaneryOutputSerializer(deaneries, many=True).data)

    @extend_schema(
        request=DeaneryCreateInputSerializer,
        responses={201: DeaneryOutputSerializer},
        tags=["org"],
        summary="Créer un doyenné (admin du diocèse)",
    )
    def post(self, request):
        serializer = DeaneryCreateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        from apps.org.models import Diocese
        try:
            diocese = Diocese.objects.get(id=data["diocese_id"])
        except Diocese.DoesNotExist:
            return Response({"detail": "Diocèse introuvable."}, status=status.HTTP_404_NOT_FOUND)
        if not user_can_admin_diocese(request.user, diocese.id):
            return Response(
                {"detail": "Accès réservé à l'administrateur du diocèse."},
                status=status.HTTP_403_FORBIDDEN,
            )
        dean = None
        if data.get("dean_id"):
            from apps.users.models import BaseUser
            dean = BaseUser.objects.filter(id=data["dean_id"]).first()
        try:
            deanery = deanery_create(name=data["name"], diocese=diocese, dean=dean)
        except ApplicationError as e:
            return _error(e)
        return Response(DeaneryOutputSerializer(deanery).data, status=status.HTTP_201_CREATED)

from drf_spectacular.openapi import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.mixins import ApiAuthMixin, PermissionClassesType
from apps.api.pagination import LimitOffsetPagination, get_paginated_response
from apps.core.exceptions import ApplicationError
from apps.tv.permissions import IsSuperAdminOrReadOnly
from apps.tv.selectors import category_get_by_slug, category_list, video_get_by_id, video_list
from apps.tv.serializers import CategorySerializer, VideoCreateUpdateSerializer, VideoListSerializer
from apps.tv.services import (
    category_create,
    category_delete,
    category_update,
    video_create,
    video_delete,
    video_update,
)
from apps.users.enums import CLERGY_PASTORAL_ROLES, UserRole


class TvCatalogApiMixin(ApiAuthMixin):
    """Pile d'authentification du projet + politique d'accès du catalogue TV.

    Ce que ``ApiAuthMixin`` apporte ici, ce sont ses ``authentication_classes``
    (JWT, session, session-en-header). Les vues TV s'appuyaient jusqu'ici sur le
    défaut global ``REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES']`` — même
    liste, mais implicite, et présentée en configuration comme un simple « filet
    de sécurité » pour les vues qui oublient le mixin. On le rend explicite : la
    résolution du porteur de jeton n'est pas cosmétique ici, c'est elle qui
    décide du cloisonnement clergé plus bas.

    En revanche, son ``permission_classes = (IsAuthenticated,)`` est
    DÉLIBÉRÉMENT remplacé. Le catalogue TV est une vitrine : la LECTURE
    (catégories et vidéos) reste ouverte aux visiteurs non connectés, et les
    tests de ``TvCatalogAccessMatrixTests`` figent ce contrat. Seule l'ÉCRITURE
    est fermée, au Super Admin, via ``IsSuperAdminOrReadOnly``.

    Ce que la lecture publique n'ouvre PAS : les catégories ``is_clergy_only``
    (« Formation ») et leurs vidéos restent filtrées par les selectors, pour un
    anonyme comme pour un fidèle, en liste comme par identifiant direct.
    """

    # Annotation explicite (comme ``ApiAuthMixin``) : sans elle, mypy voit deux
    # définitions incompatibles de ``permission_classes`` entre ce mixin et
    # ``APIView`` au moment de la fusion des bases.
    permission_classes: PermissionClassesType = (IsSuperAdminOrReadOnly,)


def _error(exc: ApplicationError) -> Response:
    return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)


def _can_view_reserved_catalog(user) -> bool:
    """Qui voit le catalogue réservé (catégories ``is_clergy_only``).

    Deux populations, pour deux raisons distinctes :

    - le **clergé**, destinataire du contenu. L'ensemble de référence est
      ``CLERGY_PASTORAL_ROLES`` (apps.users.enums) : une liste de chaînes
      recopiée ici dériverait au premier rôle pastoral ajouté ;
    - le **Super Admin**, qui administre le catalogue. Il n'a pas de
      ``pastoral_role`` : filtré comme un fidèle, il pouvait modifier et
      supprimer la catégorie « Formation » par son slug, mais ni la lire ni la
      voir en liste — donc pas l'affecter à une vidéo depuis l'UI d'admin, dont
      le sélecteur de catégorie se remplit avec ``GET /tv/categories/``.

    Ce n'est pas un élargissement du cloisonnement : anonyme et fidèle restent
    filtrés à l'identique, et le Super Admin disposait déjà de l'écriture pleine
    sur ces mêmes objets.
    """
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "pastoral_role", None) in CLERGY_PASTORAL_ROLES:
        return True
    return getattr(user, "role", None) == UserRole.SUPER_ADMIN


class CategoryListApi(TvCatalogApiMixin, APIView):
    """GET : PUBLIC (catalogue ouvert). POST : Super Admin."""

    @extend_schema(
        tags=["TV"],
        summary="List TV categories (public read)",
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT),
            OpenApiParameter("offset", OpenApiTypes.INT),
        ],
        responses={200: CategorySerializer(many=True)},
    )
    def get(self, request):
        categories = category_list(include_clergy_only=_can_view_reserved_catalog(request.user))
        return get_paginated_response(
            pagination_class=LimitOffsetPagination,
            serializer_class=CategorySerializer,
            queryset=categories,
            request=request,
            view=self,
        )

    @extend_schema(
        tags=["TV"],
        summary="Create TV category (admin)",
        request=CategorySerializer,
        responses={201: CategorySerializer, 400: OpenApiResponse(description="Validation error")},
    )
    def post(self, request):
        serializer = CategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            category = category_create(**serializer.validated_data)
        except ApplicationError as e:
            return _error(e)
        return Response(CategorySerializer(category).data, status=status.HTTP_201_CREATED)


class CategoryDetailApi(TvCatalogApiMixin, APIView):
    """GET : PUBLIC (catalogue ouvert). PUT/PATCH/DELETE : Super Admin."""

    @extend_schema(
        tags=["TV"],
        summary="Get TV category (public read)",
        responses={200: CategorySerializer, 404: OpenApiResponse(description="Not found")},
    )
    def get(self, request, slug):
        # Lecture publique : une catégorie réservée au clergé n'est pas révélée à
        # un fidèle, même en visant son slug directement (cf. category_list).
        category = category_get_by_slug(
            slug=slug,
            include_clergy_only=_can_view_reserved_catalog(request.user),
        )
        if not category:
            return Response({"error": "Category not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(CategorySerializer(category).data)

    @extend_schema(
        tags=["TV"],
        summary="Update TV category (admin)",
        request=CategorySerializer,
        responses={200: CategorySerializer},
    )
    def put(self, request, slug):
        category = category_get_by_slug(slug=slug)
        if not category:
            return Response({"error": "Category not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = CategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            category = category_update(category=category, **serializer.validated_data)
        except ApplicationError as e:
            return _error(e)
        return Response(CategorySerializer(category).data)

    @extend_schema(
        tags=["TV"],
        summary="Partial update TV category (admin)",
        request=CategorySerializer,
        responses={200: CategorySerializer},
    )
    def patch(self, request, slug):
        category = category_get_by_slug(slug=slug)
        if not category:
            return Response({"error": "Category not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = CategorySerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            category = category_update(category=category, **serializer.validated_data)
        except ApplicationError as e:
            return _error(e)
        return Response(CategorySerializer(category).data)

    @extend_schema(
        tags=["TV"],
        summary="Delete TV category (admin)",
        responses={204: None, 404: OpenApiResponse(description="Not found")},
    )
    def delete(self, request, slug):
        category = category_get_by_slug(slug=slug)
        if not category:
            return Response({"error": "Category not found."}, status=status.HTTP_404_NOT_FOUND)
        category_delete(category=category)
        return Response(status=status.HTTP_204_NO_CONTENT)


class VideoListApi(TvCatalogApiMixin, APIView):
    """GET : PUBLIC (catalogue ouvert). POST : Super Admin."""

    @extend_schema(
        tags=["TV"],
        summary="List TV videos (public read)",
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT),
            OpenApiParameter("offset", OpenApiTypes.INT),
            OpenApiParameter("category", OpenApiTypes.STR, description="Filter by category slug"),
            OpenApiParameter("is_live", OpenApiTypes.STR, enum=["true", "false"]),
            OpenApiParameter("is_pinned_live", OpenApiTypes.STR, enum=["true", "false"]),
        ],
        responses={200: VideoListSerializer(many=True)},
    )
    def get(self, request):
        videos = video_list(
            category_slug=request.query_params.get("category"),
            is_live=request.query_params.get("is_live"),
            is_pinned_live=request.query_params.get("is_pinned_live"),
            include_clergy_only=_can_view_reserved_catalog(request.user),
        )
        return get_paginated_response(
            pagination_class=LimitOffsetPagination,
            serializer_class=VideoListSerializer,
            queryset=videos,
            request=request,
            view=self,
        )

    @extend_schema(
        tags=["TV"],
        summary="Create TV video (admin)",
        request=VideoCreateUpdateSerializer,
        responses={201: VideoListSerializer},
    )
    def post(self, request):
        serializer = VideoCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            video = video_create(**serializer.validated_data)
        except ApplicationError as e:
            return _error(e)
        return Response(VideoListSerializer(video).data, status=status.HTTP_201_CREATED)


class VideoDetailApi(TvCatalogApiMixin, APIView):
    """GET : PUBLIC (catalogue ouvert). PUT/PATCH/DELETE : Super Admin."""

    @extend_schema(
        tags=["TV"],
        summary="Get TV video (public read)",
        responses={200: VideoListSerializer, 404: OpenApiResponse(description="Not found")},
    )
    def get(self, request, video_id):
        # Même cloisonnement que la liste : sans ce filtre, une vidéo « Formation »
        # (clergé) restait atteignable en devinant son id.
        video = video_get_by_id(
            video_id=video_id,
            include_clergy_only=_can_view_reserved_catalog(request.user),
        )
        if not video:
            return Response({"error": "Video not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(VideoListSerializer(video).data)

    @extend_schema(
        tags=["TV"],
        summary="Update TV video (admin)",
        request=VideoCreateUpdateSerializer,
        responses={200: VideoListSerializer},
    )
    def put(self, request, video_id):
        video = video_get_by_id(video_id=video_id)
        if not video:
            return Response({"error": "Video not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = VideoCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            updated = video_update(video=video, **serializer.validated_data)
        except ApplicationError as e:
            return _error(e)
        return Response(VideoListSerializer(updated).data)

    @extend_schema(
        tags=["TV"],
        summary="Partial update TV video (admin)",
        request=VideoCreateUpdateSerializer,
        responses={200: VideoListSerializer},
    )
    def patch(self, request, video_id):
        video = video_get_by_id(video_id=video_id)
        if not video:
            return Response({"error": "Video not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = VideoCreateUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            updated = video_update(video=video, **serializer.validated_data)
        except ApplicationError as e:
            return _error(e)
        return Response(VideoListSerializer(updated).data)

    @extend_schema(
        tags=["TV"],
        summary="Delete TV video (admin)",
        responses={204: None, 404: OpenApiResponse(description="Not found")},
    )
    def delete(self, request, video_id):
        video = video_get_by_id(video_id=video_id)
        if not video:
            return Response({"error": "Video not found."}, status=status.HTTP_404_NOT_FOUND)
        video_delete(video=video)
        return Response(status=status.HTTP_204_NO_CONTENT)

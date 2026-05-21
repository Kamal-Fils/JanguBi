from drf_spectacular.openapi import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.mixins import ApiAuthMixin
from apps.api.pagination import LimitOffsetPagination, get_paginated_response
from apps.core.exceptions import ApplicationError
from apps.tv.permissions import IsAdminOrReadOnly
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

CLERGY_ROLES = {"diacre", "pretre", "eveque", "archeveque", "religieux"}


def _error(exc: ApplicationError) -> Response:
    return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)


def _is_clergy(user) -> bool:
    return getattr(user, "pastoral_role", None) in CLERGY_ROLES


class CategoryListApi(APIView):
    def get_permissions(self):
        if self.request.method in ("POST",):
            return [IsAuthenticated(), IsAdminOrReadOnly()]
        return [IsAdminOrReadOnly()]

    @extend_schema(
        tags=["TV"],
        summary="List TV categories",
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT),
            OpenApiParameter("offset", OpenApiTypes.INT),
        ],
        responses={200: CategorySerializer(many=True)},
    )
    def get(self, request):
        clergy = _is_clergy(request.user) if request.user.is_authenticated else False
        categories = category_list(clergy_only=clergy)
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


class CategoryDetailApi(APIView):
    def get_permissions(self):
        if self.request.method in ("PUT", "PATCH", "DELETE"):
            return [IsAuthenticated(), IsAdminOrReadOnly()]
        return [IsAdminOrReadOnly()]

    @extend_schema(
        tags=["TV"],
        summary="Get TV category",
        responses={200: CategorySerializer, 404: OpenApiResponse(description="Not found")},
    )
    def get(self, request, slug):
        category = category_get_by_slug(slug=slug)
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


class VideoListApi(APIView):
    def get_permissions(self):
        if self.request.method in ("POST",):
            return [IsAuthenticated(), IsAdminOrReadOnly()]
        return [IsAdminOrReadOnly()]

    @extend_schema(
        tags=["TV"],
        summary="List TV videos",
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
        clergy = _is_clergy(request.user) if request.user.is_authenticated else False
        videos = video_list(
            category_slug=request.query_params.get("category"),
            is_live=request.query_params.get("is_live"),
            is_pinned_live=request.query_params.get("is_pinned_live"),
            include_clergy_only=clergy,
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


class VideoDetailApi(APIView):
    def get_permissions(self):
        if self.request.method in ("PUT", "PATCH", "DELETE"):
            return [IsAuthenticated(), IsAdminOrReadOnly()]
        return [IsAdminOrReadOnly()]

    @extend_schema(
        tags=["TV"],
        summary="Get TV video",
        responses={200: VideoListSerializer, 404: OpenApiResponse(description="Not found")},
    )
    def get(self, request, video_id):
        video = video_get_by_id(video_id=video_id)
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

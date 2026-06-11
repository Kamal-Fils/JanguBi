from drf_spectacular.openapi import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.pagination import LimitOffsetPagination, get_paginated_response
from apps.core.exceptions import ApplicationError
from apps.tv.permissions import IsAdminOrReadOnly
from apps.tv.selectors import category_get_by_slug, category_list, video_get_by_id, video_list
from apps.tv.serializers import CategorySerializer, VideoCreateUpdateSerializer, VideoListSerializer
from apps.tv.services import category_create, category_delete, category_update, video_create, video_delete, video_update


def _error(exc: ApplicationError) -> Response:
    return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)


class CategoryListApi(APIView):
    def get_permissions(self):
        if self.request.method in ("POST",):
            return [IsAuthenticated(), IsAdminOrReadOnly()]
        return [IsAdminOrReadOnly()]

    @extend_schema(
        tags=["TV"],
        summary="List TV categories",
        description="Returns all TV categories ordered by `order` then `name`.",
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT, description="Number of results per page (default 20)"),
            OpenApiParameter("offset", OpenApiTypes.INT, description="Pagination offset (default 0)"),
        ],
        responses={200: CategorySerializer(many=True)},
    )
    def get(self, request):
        categories = category_list()
        return get_paginated_response(
            pagination_class=LimitOffsetPagination,
            serializer_class=CategorySerializer,
            queryset=categories,
            request=request,
            view=self,
        )

    @extend_schema(
        tags=["TV"],
        summary="Create TV category",
        description="Create a new TV category. Admin only.",
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
        summary="Get TV category details",
        description="Retrieve a TV category by slug.",
        responses={200: CategorySerializer, 404: OpenApiResponse(description="Category not found")},
    )
    def get(self, request, slug):
        category = category_get_by_slug(slug=slug)
        if not category:
            return Response({"error": "Category not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(CategorySerializer(category).data)

    @extend_schema(
        tags=["TV"],
        summary="Update TV category",
        description="Update a TV category by slug. Admin only.",
        request=CategorySerializer,
        responses={200: CategorySerializer, 400: OpenApiResponse(description="Validation error"), 404: OpenApiResponse(description="Category not found")},
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
        summary="Partially update TV category",
        description="Partially update a TV category by slug. Admin only.",
        request=CategorySerializer,
        responses={200: CategorySerializer, 400: OpenApiResponse(description="Validation error"), 404: OpenApiResponse(description="Category not found")},
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
        summary="Delete TV category",
        description="Delete a TV category by slug. Admin only.",
        responses={204: OpenApiResponse(description="Deleted"), 404: OpenApiResponse(description="Category not found")},
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
        description="Returns all videos ordered by pin/live status and creation date.",
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT, description="Number of results per page (default 20)"),
            OpenApiParameter("offset", OpenApiTypes.INT, description="Pagination offset (default 0)"),
            OpenApiParameter("category", OpenApiTypes.STR, description="Filter by category slug"),
            OpenApiParameter("is_live", OpenApiTypes.STR, enum=["true", "false"], description="Filter by live status"),
            OpenApiParameter("is_pinned_live", OpenApiTypes.STR, enum=["true", "false"], description="Filter by pinned live status"),
        ],
        responses={200: VideoListSerializer(many=True)},
    )
    def get(self, request):
        videos = video_list(
            category_slug=request.query_params.get("category"),
            is_live=request.query_params.get("is_live"),
            is_pinned_live=request.query_params.get("is_pinned_live"),
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
        summary="Create TV video",
        description="Create a new TV video with `category_slug` and a valid YouTube URL. Admin only.",
        request=VideoCreateUpdateSerializer,
        responses={201: VideoListSerializer, 400: OpenApiResponse(description="Validation error")},
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
        summary="Get TV video details",
        description="Retrieve a TV video by id.",
        responses={200: VideoListSerializer, 404: OpenApiResponse(description="Video not found")},
    )
    def get(self, request, video_id):
        video = video_get_by_id(video_id=video_id)
        if not video:
            return Response({"error": "Video not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(VideoListSerializer(video).data)

    @extend_schema(
        tags=["TV"],
        summary="Update TV video",
        description="Update a TV video by id. Admin only.",
        request=VideoCreateUpdateSerializer,
        responses={200: VideoListSerializer, 400: OpenApiResponse(description="Validation error"), 404: OpenApiResponse(description="Video not found")},
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
        summary="Partially update TV video",
        description="Partially update a TV video by id. Admin only.",
        request=VideoCreateUpdateSerializer,
        responses={200: VideoListSerializer, 400: OpenApiResponse(description="Validation error"), 404: OpenApiResponse(description="Video not found")},
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
        summary="Delete TV video",
        description="Delete a TV video by id. Admin only.",
        responses={204: OpenApiResponse(description="Deleted"), 404: OpenApiResponse(description="Video not found")},
    )
    def delete(self, request, video_id):
        video = video_get_by_id(video_id=video_id)
        if not video:
            return Response({"error": "Video not found."}, status=status.HTTP_404_NOT_FOUND)
        video_delete(video=video)
        return Response(status=status.HTTP_204_NO_CONTENT)

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import ApplicationError
from apps.tv.models import Category, Video
from apps.tv.permissions import IsAdminOrReadOnly
from apps.tv.serializers import CategorySerializer, VideoCreateUpdateSerializer, VideoListSerializer


def _error(exc: ApplicationError) -> Response:
    return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)


class CategoryListApi(APIView):
    permission_classes = [IsAdminOrReadOnly]

    @extend_schema(
        tags=["TV"],
        summary="List TV categories",
        description="Returns all TV categories ordered by `order` then `name`.",
        responses=CategorySerializer(many=True),
    )
    def get(self, request):
        categories = Category.objects.all().order_by("order", "name")
        serializer = CategorySerializer(categories, many=True)
        return Response(serializer.data)

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
        category = serializer.save()
        return Response(CategorySerializer(category).data, status=status.HTTP_201_CREATED)


class CategoryDetailApi(APIView):
    permission_classes = [IsAdminOrReadOnly]

    def _get_category(self, slug):
        category = Category.objects.filter(slug=slug).first()
        if not category:
            return None
        return category

    @extend_schema(
        tags=["TV"],
        summary="Get TV category details",
        description="Retrieve a TV category by slug.",
        responses={200: CategorySerializer, 404: OpenApiResponse(description="Category not found")},
    )
    def get(self, request, slug):
        category = self._get_category(slug)
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
        category = self._get_category(slug)
        if not category:
            return Response({"error": "Category not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = CategorySerializer(category, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @extend_schema(
        tags=["TV"],
        summary="Partially update TV category",
        description="Partially update a TV category by slug. Admin only.",
        request=CategorySerializer,
        responses={200: CategorySerializer, 400: OpenApiResponse(description="Validation error"), 404: OpenApiResponse(description="Category not found")},
    )
    def patch(self, request, slug):
        category = self._get_category(slug)
        if not category:
            return Response({"error": "Category not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = CategorySerializer(category, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @extend_schema(
        tags=["TV"],
        summary="Delete TV category",
        description="Delete a TV category by slug. Admin only.",
        responses={204: OpenApiResponse(description="Deleted"), 404: OpenApiResponse(description="Category not found")},
    )
    def delete(self, request, slug):
        category = self._get_category(slug)
        if not category:
            return Response({"error": "Category not found."}, status=status.HTTP_404_NOT_FOUND)
        category.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class VideoListApi(APIView):
    permission_classes = [IsAdminOrReadOnly]

    @extend_schema(
        tags=["TV"],
        summary="List TV videos",
        description="Returns all videos ordered by pin/live status and creation date.",
        responses=VideoListSerializer(many=True),
    )
    def get(self, request):
        videos = Video.objects.select_related("category").all()

        category_slug = request.query_params.get("category")
        if category_slug:
            videos = videos.filter(category__slug=category_slug)

        is_live = request.query_params.get("is_live")
        if is_live in {"true", "false"}:
            videos = videos.filter(is_live=(is_live == "true"))

        is_pinned_live = request.query_params.get("is_pinned_live")
        if is_pinned_live in {"true", "false"}:
            videos = videos.filter(is_pinned_live=(is_pinned_live == "true"))

        serializer = VideoListSerializer(videos, many=True)
        return Response(serializer.data)

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
            video = serializer.save()
        except ApplicationError as e:
            return _error(e)
        return Response(VideoListSerializer(video).data, status=status.HTTP_201_CREATED)


class VideoDetailApi(APIView):
    permission_classes = [IsAdminOrReadOnly]

    def _get_video(self, video_id):
        video = Video.objects.select_related("category").filter(id=video_id).first()
        if not video:
            return None
        return video

    @extend_schema(
        tags=["TV"],
        summary="Get TV video details",
        description="Retrieve a TV video by id.",
        responses={200: VideoListSerializer, 404: OpenApiResponse(description="Video not found")},
    )
    def get(self, request, video_id):
        video = self._get_video(video_id)
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
        video = self._get_video(video_id)
        if not video:
            return Response({"error": "Video not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = VideoCreateUpdateSerializer(video, data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        return Response(VideoListSerializer(updated).data)

    @extend_schema(
        tags=["TV"],
        summary="Partially update TV video",
        description="Partially update a TV video by id. Admin only.",
        request=VideoCreateUpdateSerializer,
        responses={200: VideoListSerializer, 400: OpenApiResponse(description="Validation error"), 404: OpenApiResponse(description="Video not found")},
    )
    def patch(self, request, video_id):
        video = self._get_video(video_id)
        if not video:
            return Response({"error": "Video not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = VideoCreateUpdateSerializer(video, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        return Response(VideoListSerializer(updated).data)

    @extend_schema(
        tags=["TV"],
        summary="Delete TV video",
        description="Delete a TV video by id. Admin only.",
        responses={204: OpenApiResponse(description="Deleted"), 404: OpenApiResponse(description="Video not found")},
    )
    def delete(self, request, video_id):
        video = self._get_video(video_id)
        if not video:
            return Response({"error": "Video not found."}, status=status.HTTP_404_NOT_FOUND)
        video.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

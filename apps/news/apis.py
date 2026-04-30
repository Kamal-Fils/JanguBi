from uuid import UUID

from django.shortcuts import get_object_or_404
from drf_spectacular.openapi import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.mixins import ApiAuthMixin
from apps.api.pagination import LimitOffsetPagination, get_paginated_response
from apps.core.exceptions import ApplicationError
from apps.news.models import Article
from apps.news.permissions import CanUnpublishArticle, IsArticleEditor
from apps.news.selectors import (
    article_get,
    article_list,
    article_list_for_diocese,
    article_list_for_parish,
    article_list_global,
    category_list,
)
from apps.news.serializers import (
    ArticleCategoryOutputSerializer,
    ArticleCreateInputSerializer,
    ArticleDetailOutputSerializer,
    ArticleListOutputSerializer,
    ArticleUnpublishInputSerializer,
    ArticleUpdateInputSerializer,
)
from apps.news.services import (
    article_create,
    article_delete,
    article_increment_views,
    article_publish,
    article_unpublish,
    article_update,
)


def _error(exc: ApplicationError) -> Response:
    return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Catégories (publique)
# ---------------------------------------------------------------------------


class CategoryListApi(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        responses={200: ArticleCategoryOutputSerializer(many=True)},
        tags=["news"],
        summary="Lister les catégories d'articles actives",
    )
    def get(self, request):
        categories = category_list(active_only=True)
        return Response(ArticleCategoryOutputSerializer(categories, many=True).data)


# ---------------------------------------------------------------------------
# Feed global (publique)
# ---------------------------------------------------------------------------


class ArticleGlobalListApi(APIView):
    permission_classes = [AllowAny]

    class Pagination(LimitOffsetPagination):
        default_limit = 20

    @extend_schema(
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT, description="Nombre de résultats (défaut 20)"),
            OpenApiParameter("offset", OpenApiTypes.INT, description="Décalage pagination"),
            OpenApiParameter("category", OpenApiTypes.STR, description="Filtrer par slug de catégorie"),
            OpenApiParameter("search", OpenApiTypes.STR, description="Recherche dans le titre"),
        ],
        responses={200: ArticleListOutputSerializer(many=True)},
        tags=["news"],
        summary="Feed global — articles publiés pour toute l'Église du Sénégal",
    )
    def get(self, request):
        qs = article_list_global(
            category_slug=request.query_params.get("category"),
            search=request.query_params.get("search"),
        )
        return get_paginated_response(
            pagination_class=self.Pagination,
            serializer_class=ArticleListOutputSerializer,
            queryset=qs,
            request=request,
            view=self,
        )


# ---------------------------------------------------------------------------
# Feed paroisse (auth requise)
# ---------------------------------------------------------------------------


class ArticleParishListApi(ApiAuthMixin, APIView):
    class Pagination(LimitOffsetPagination):
        default_limit = 20

    @extend_schema(
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT, description="Nombre de résultats"),
            OpenApiParameter("offset", OpenApiTypes.INT, description="Décalage pagination"),
            OpenApiParameter("category", OpenApiTypes.STR, description="Filtrer par slug de catégorie"),
            OpenApiParameter("search", OpenApiTypes.STR, description="Recherche dans le titre"),
        ],
        responses={200: ArticleListOutputSerializer(many=True)},
        tags=["news"],
        summary="Articles publiés d'une paroisse",
    )
    def get(self, request, parish_id: int):
        qs = article_list_for_parish(
            parish_id=parish_id,
            category_slug=request.query_params.get("category"),
            search=request.query_params.get("search"),
        )
        return get_paginated_response(
            pagination_class=self.Pagination,
            serializer_class=ArticleListOutputSerializer,
            queryset=qs,
            request=request,
            view=self,
        )


class ArticleMyParishListApi(ApiAuthMixin, APIView):
    """Articles de la paroisse principale du fidèle connecté."""

    class Pagination(LimitOffsetPagination):
        default_limit = 20

    @extend_schema(
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT, description="Nombre de résultats"),
            OpenApiParameter("offset", OpenApiTypes.INT, description="Décalage pagination"),
            OpenApiParameter("category", OpenApiTypes.STR, description="Filtrer par slug de catégorie"),
            OpenApiParameter("search", OpenApiTypes.STR, description="Recherche dans le titre"),
        ],
        responses={200: ArticleListOutputSerializer(many=True)},
        tags=["news"],
        summary="Articles de ma paroisse (paroisse principale du profil)",
    )
    def get(self, request):
        profile = getattr(request.user, "profile", None)
        parish_id = getattr(profile, "primary_parish", None) if profile else None

        if not parish_id:
            return Response({"results": [], "count": 0, "next": None, "previous": None})

        qs = article_list_for_parish(
            parish_id=parish_id,
            category_slug=request.query_params.get("category"),
            search=request.query_params.get("search"),
        )
        return get_paginated_response(
            pagination_class=self.Pagination,
            serializer_class=ArticleListOutputSerializer,
            queryset=qs,
            request=request,
            view=self,
        )


# ---------------------------------------------------------------------------
# Feed diocèse (auth requise)
# ---------------------------------------------------------------------------


class ArticleDioceseListApi(ApiAuthMixin, APIView):
    class Pagination(LimitOffsetPagination):
        default_limit = 20

    @extend_schema(
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT, description="Nombre de résultats"),
            OpenApiParameter("offset", OpenApiTypes.INT, description="Décalage pagination"),
            OpenApiParameter("category", OpenApiTypes.STR, description="Filtrer par slug de catégorie"),
            OpenApiParameter("search", OpenApiTypes.STR, description="Recherche dans le titre"),
        ],
        responses={200: ArticleListOutputSerializer(many=True)},
        tags=["news"],
        summary="Articles publiés d'un diocèse",
    )
    def get(self, request, diocese_id: int):
        qs = article_list_for_diocese(
            diocese_id=diocese_id,
            category_slug=request.query_params.get("category"),
            search=request.query_params.get("search"),
        )
        return get_paginated_response(
            pagination_class=self.Pagination,
            serializer_class=ArticleListOutputSerializer,
            queryset=qs,
            request=request,
            view=self,
        )


# ---------------------------------------------------------------------------
# Détail article (publique)
# ---------------------------------------------------------------------------


class ArticleDetailApi(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        responses={200: ArticleDetailOutputSerializer},
        tags=["news"],
        summary="Détail d'un article publié",
    )
    def get(self, request, article_id: UUID):
        article = article_get(article_id=str(article_id))
        if article is None or article.status != Article.Status.PUBLISHED:
            return Response({"detail": "Article introuvable."}, status=status.HTTP_404_NOT_FOUND)
        article_increment_views(article=article)
        return Response(ArticleDetailOutputSerializer(article).data)


# ---------------------------------------------------------------------------
# Administration — liste tous statuts
# ---------------------------------------------------------------------------


class AdminArticleListApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsArticleEditor]

    class Pagination(LimitOffsetPagination):
        default_limit = 20

    @extend_schema(
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT, description="Nombre de résultats"),
            OpenApiParameter("offset", OpenApiTypes.INT, description="Décalage pagination"),
            OpenApiParameter("status", OpenApiTypes.STR, enum=["draft", "published", "unpublished"], description="Filtrer par statut"),
            OpenApiParameter("scope_type", OpenApiTypes.STR, enum=["global", "diocese", "parish"], description="Filtrer par portée"),
            OpenApiParameter("category", OpenApiTypes.STR, description="Filtrer par slug catégorie"),
            OpenApiParameter("search", OpenApiTypes.STR, description="Recherche dans le titre"),
        ],
        responses={200: ArticleListOutputSerializer(many=True)},
        tags=["news-admin"],
        summary="[Admin] Lister tous les articles (tous statuts)",
    )
    def get(self, request):
        qs = article_list(
            status=request.query_params.get("status", "") or "",
            scope_type=request.query_params.get("scope_type") or None,
            category_slug=request.query_params.get("category") or None,
            search=request.query_params.get("search") or None,
        )
        return get_paginated_response(
            pagination_class=self.Pagination,
            serializer_class=ArticleListOutputSerializer,
            queryset=qs,
            request=request,
            view=self,
        )


# ---------------------------------------------------------------------------
# Administration — CRUD
# ---------------------------------------------------------------------------


class AdminArticleCreateApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsArticleEditor]

    @extend_schema(
        request=ArticleCreateInputSerializer,
        responses={201: ArticleDetailOutputSerializer},
        tags=["news-admin"],
        summary="[Admin] Créer un article",
    )
    def post(self, request):
        serializer = ArticleCreateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            article = article_create(author=request.user, **serializer.validated_data)
        except ApplicationError as exc:
            return _error(exc)
        return Response(ArticleDetailOutputSerializer(article).data, status=status.HTTP_201_CREATED)


class AdminArticleDetailApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsArticleEditor]

    @extend_schema(
        responses={200: ArticleDetailOutputSerializer},
        tags=["news-admin"],
        summary="[Admin] Détail d'un article (tous statuts)",
    )
    def get(self, request, article_id: UUID):
        article = article_get(article_id=str(article_id))
        if article is None:
            return Response({"detail": "Article introuvable."}, status=status.HTTP_404_NOT_FOUND)
        return Response(ArticleDetailOutputSerializer(article).data)


class AdminArticleUpdateApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsArticleEditor]

    @extend_schema(
        request=ArticleUpdateInputSerializer,
        responses={200: ArticleDetailOutputSerializer},
        tags=["news-admin"],
        summary="[Admin] Modifier un article",
    )
    def patch(self, request, article_id: UUID):
        article = get_object_or_404(Article, pk=article_id)
        serializer = ArticleUpdateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            article = article_update(article=article, editor=request.user, **serializer.validated_data)
        except ApplicationError as exc:
            return _error(exc)
        return Response(ArticleDetailOutputSerializer(article).data)


class AdminArticlePublishApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsArticleEditor]

    @extend_schema(
        responses={200: ArticleDetailOutputSerializer},
        tags=["news-admin"],
        summary="[Admin] Publier un article",
    )
    def post(self, request, article_id: UUID):
        article = get_object_or_404(Article, pk=article_id)
        try:
            article = article_publish(article=article, editor=request.user)
        except ApplicationError as exc:
            return _error(exc)
        return Response(ArticleDetailOutputSerializer(article).data)


class AdminArticleUnpublishApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, CanUnpublishArticle]

    @extend_schema(
        request=ArticleUnpublishInputSerializer,
        responses={200: ArticleDetailOutputSerializer},
        tags=["news-admin"],
        summary="[Admin] Dépublier un article",
    )
    def post(self, request, article_id: UUID):
        article = get_object_or_404(Article, pk=article_id)
        serializer = ArticleUnpublishInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            article = article_unpublish(
                article=article,
                editor=request.user,
                reason=serializer.validated_data.get("reason", ""),
            )
        except ApplicationError as exc:
            return _error(exc)
        return Response(ArticleDetailOutputSerializer(article).data)


class AdminArticleDeleteApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsArticleEditor]

    @extend_schema(
        responses={204: None},
        tags=["news-admin"],
        summary="[Admin] Supprimer un article (brouillon ou dépublié uniquement)",
    )
    def delete(self, request, article_id: UUID):
        article = get_object_or_404(Article, pk=article_id)
        try:
            article_delete(article=article, editor=request.user)
        except ApplicationError as exc:
            return _error(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)

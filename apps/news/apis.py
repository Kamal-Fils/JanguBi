from uuid import UUID

from django.shortcuts import get_object_or_404
from drf_spectacular.openapi import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.mixins import ApiAuthMixin
from apps.api.pagination import (
    LimitOffsetPagination,
    get_paginated_response,
    paginated_response_serializer,
)
from apps.core.exceptions import ApplicationError
from apps.news.models import Article
from apps.news.permissions import CanUnpublishArticle, IsArticleEditor
from apps.news.selectors import (
    article_get,
    article_list,
    article_list_for_diocese,
    article_list_for_parish,
    article_list_for_user,
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
        # A2 — borner la lecture à l'appartenance/autorité : un fidèle ne lit que
        # le fil des paroisses dont il est membre ; le clergé/admin, celles qu'il
        # administre. Pas de lecture d'une paroisse arbitraire par id.
        from apps.users.scoping import user_can_admin_parish

        scope = request.user.get_scope_ids()
        if parish_id not in scope["parish_ids"] and not user_can_admin_parish(
            request.user, parish_id
        ):
            return Response(
                {"detail": "Vous n'êtes pas membre de cette paroisse."},
                status=status.HTTP_403_FORBIDDEN,
            )

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


class ArticleFeedApi(ApiAuthMixin, APIView):
    """Fil d'actualités AGRÉGÉ de l'utilisateur connecté (Chantier 7b) :
    global ∪ église ∪ paroisse ∪ diocèse de toutes ses appartenances (C3a)."""

    class Pagination(LimitOffsetPagination):
        default_limit = 20

    @extend_schema(
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT, description="Nombre de résultats"),
            OpenApiParameter("offset", OpenApiTypes.INT, description="Décalage pagination"),
            OpenApiParameter("category", OpenApiTypes.STR, description="Filtrer par slug de catégorie"),
            OpenApiParameter("search", OpenApiTypes.STR, description="Recherche dans le titre"),
            OpenApiParameter(
                "scope_type",
                OpenApiTypes.STR,
                enum=["global", "diocese", "parish", "church"],
                description="Filtrer le fil par portée (borné aux appartenances de l'utilisateur)",
            ),
            OpenApiParameter(
                "scope_id",
                OpenApiTypes.INT,
                description="ID de l'entité de portée (requis pour diocese/parish/church)",
            ),
        ],
        responses={200: paginated_response_serializer(ArticleListOutputSerializer)},
        tags=["news"],
        summary="Fil d'actualités agrégé (toutes mes portées, filtrable par portée)",
    )
    def get(self, request):
        scope_type = request.query_params.get("scope_type")
        scope_id = self._validate_scope_filter(request, scope_type)
        if isinstance(scope_id, Response):  # erreur de validation (400/403)
            return scope_id

        qs = article_list_for_user(
            user=request.user, scope_type=scope_type, scope_id=scope_id
        )
        if category := request.query_params.get("category"):
            qs = qs.filter(category__slug=category)
        if search := request.query_params.get("search"):
            qs = qs.filter(title__icontains=search)
        return get_paginated_response(
            pagination_class=self.Pagination,
            serializer_class=ArticleListOutputSerializer,
            queryset=qs,
            request=request,
            view=self,
        )

    @staticmethod
    def _validate_scope_filter(request, scope_type):
        """Valide ?scope_type=&scope_id= et BORNE aux appartenances de l'utilisateur.

        Retourne le scope_id résolu (int|None), ou une Response d'erreur :
        - 400 si scope_type inconnu, ou scope_id manquant/non numérique pour une
          portée territoriale ;
        - 403 si la portée demandée n'est PAS dans les appartenances (ne rouvre pas
          le cloisonnement).
        """
        if not scope_type:
            return None
        if scope_type == Article.ScopeType.GLOBAL:
            return None  # scope_id ignoré pour global
        if scope_type not in {
            Article.ScopeType.DIOCESE,
            Article.ScopeType.PARISH,
            Article.ScopeType.CHURCH,
        }:
            return Response({"detail": "Portée invalide."}, status=status.HTTP_400_BAD_REQUEST)

        raw = request.query_params.get("scope_id")
        if not raw or not raw.lstrip("-").isdigit():
            return Response(
                {"detail": "scope_id requis pour cette portée."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        scope_id = int(raw)

        ids = request.user.get_scope_ids()
        allowed = {
            Article.ScopeType.CHURCH: ids["church_ids"],
            Article.ScopeType.PARISH: ids["parish_ids"],
            Article.ScopeType.DIOCESE: ids["diocese_ids"],
        }[scope_type]
        if scope_id not in allowed:
            return Response(
                {"detail": "Portée hors de vos appartenances."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return scope_id


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
        from apps.users.selectors import profile_get

        profile = profile_get(user=request.user)
        parish_id = profile.primary_parish if profile else None

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
        # A2 — borner à l'appartenance/autorité diocésaine (cf. ArticleParishListApi).
        from apps.users.scoping import user_can_admin_diocese

        scope = request.user.get_scope_ids()
        if diocese_id not in scope["diocese_ids"] and not user_can_admin_diocese(
            request.user, diocese_id
        ):
            return Response(
                {"detail": "Vous n'êtes pas membre de ce diocèse."},
                status=status.HTTP_403_FORBIDDEN,
            )

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
            OpenApiParameter("scope_type", OpenApiTypes.STR, enum=["global", "diocese", "parish", "church"], description="Filtrer par portée"),
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

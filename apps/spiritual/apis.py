from django.utils import timezone
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
from apps.spiritual.selectors import (
    reflection_get,
    reflection_list_for_user,
    reflection_my_today,
    reflection_today_for_user,
)
from apps.spiritual.serializers import (
    ReflectionOutputSerializer,
    ReflectionUpsertInputSerializer,
)
from apps.spiritual.services import (
    is_reflection_editor,
    reflection_delete,
    reflection_upsert,
)


def _error(exc: ApplicationError) -> Response:
    return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)


class ReflectionTodayApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: ReflectionOutputSerializer},
        tags=["spiritual"],
        summary="Réflexion pastorale du jour (scopée aux appartenances de l'utilisateur)",
    )
    def get(self, request):
        reflection = reflection_today_for_user(user=request.user)
        if reflection is None:
            # 200 + null : le front distingue « pas de réflexion » d'une erreur (≠ 404).
            return Response(None, status=status.HTTP_200_OK)
        return Response(ReflectionOutputSerializer(reflection).data)


class ReflectionMyTodayApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: ReflectionOutputSerializer},
        tags=["spiritual"],
        summary="Ma réflexion du jour (auteur connecté)",
    )
    def get(self, request):
        reflection = reflection_my_today(user=request.user)
        if reflection is None:
            return Response(None, status=status.HTTP_200_OK)
        return Response(ReflectionOutputSerializer(reflection).data)


class ReflectionListCreateApi(ApiAuthMixin, APIView):
    class Pagination(LimitOffsetPagination):
        default_limit = 20

    @extend_schema(
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT, description="Nombre de résultats (défaut 20)"),
            OpenApiParameter("offset", OpenApiTypes.INT, description="Décalage pagination"),
        ],
        responses={200: paginated_response_serializer(ReflectionOutputSerializer)},
        tags=["spiritual"],
        summary="Historique des réflexions visibles (scopé aux appartenances)",
    )
    def get(self, request):
        reflections = reflection_list_for_user(user=request.user)
        return get_paginated_response(
            pagination_class=self.Pagination,
            serializer_class=ReflectionOutputSerializer,
            queryset=reflections,
            request=request,
            view=self,
        )

    @extend_schema(
        request=ReflectionUpsertInputSerializer,
        responses={201: ReflectionOutputSerializer},
        tags=["spiritual"],
        summary="Publier / mettre à jour ma réflexion (clergé, scopée)",
    )
    def post(self, request):
        if not is_reflection_editor(request.user):
            return Response(
                {"detail": "Seul le clergé (prêtre, évêque, archevêque) peut publier une réflexion."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ReflectionUpsertInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        if not data.get("reflection_date"):
            data["reflection_date"] = timezone.localdate()

        try:
            reflection = reflection_upsert(author=request.user, **data)
        except ApplicationError as exc:
            return _error(exc)

        return Response(
            ReflectionOutputSerializer(reflection).data, status=status.HTTP_201_CREATED
        )


class ReflectionDetailApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: ReflectionOutputSerializer},
        tags=["spiritual"],
        summary="Détail d'une réflexion",
    )
    def get(self, request, reflection_id):
        reflection = reflection_get(reflection_id=reflection_id)
        if reflection is None:
            return Response({"detail": "Réflexion introuvable."}, status=status.HTTP_404_NOT_FOUND)
        return Response(ReflectionOutputSerializer(reflection).data)

    @extend_schema(
        responses={204: None},
        tags=["spiritual"],
        summary="Supprimer une réflexion (auteur ou admin)",
    )
    def delete(self, request, reflection_id):
        reflection = reflection_get(reflection_id=reflection_id)
        if reflection is None:
            return Response({"detail": "Réflexion introuvable."}, status=status.HTTP_404_NOT_FOUND)
        try:
            reflection_delete(reflection=reflection, editor=request.user)
        except ApplicationError as exc:
            return _error(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)

from asgiref.sync import async_to_sync
from django.db import transaction
from django.utils.decorators import method_decorator
from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from apps.api.mixins import ApiAuthMixin
from apps.rag.serializers import RagQuerySerializer, RagResponseSerializer
from apps.rag.service import RAGService


@method_decorator(transaction.non_atomic_requests, name="dispatch")
class RagChatApi(ApiAuthMixin, APIView):
    # Throttle effectif (scope 'rag' => rate défini dans REST_FRAMEWORK).
    # Auparavant UserRateThrottle sans rate 'user' => throttle inopérant.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "rag"

    @extend_schema(
        request=RagQuerySerializer,
        responses={200: RagResponseSerializer},
        tags=["RAG"],
        summary="Ask a question to the AI assistant using RAG (Retrieval-Augmented Generation)"
    )
    def post(self, request):
        serializer = RagQuerySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        query = serializer.validated_data["query"]

        # Instance par requête : reflète la config courante (settings/overrides) et
        # évite un état partagé figé à l'import. L'init est légère (le modèle
        # d'embeddings est, lui, mémoïsé globalement via lru_cache).
        rag_service = RAGService()

        # DRF regular APIView does not support async methods properly, so we bridge to sync
        result = async_to_sync(rag_service.process_query)(query)
        
        resp_serializer = RagResponseSerializer(data=result)
        resp_serializer.is_valid(raise_exception=True)

        return Response(resp_serializer.validated_data, status=status.HTTP_200_OK)

from drf_spectacular.openapi import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.mixins import ApiAuthMixin
from apps.api.pagination import LimitOffsetPagination, get_paginated_response
from apps.core.exceptions import ApplicationError
from apps.users.permissions import IsOnboardingCompleted

from .selectors import (
    CLERGY_PASTORAL_ROLES,
    mass_intention_get,
    mass_intention_list_for_requestor,
    mass_intention_list_pending,
)
from .serializers import (
    MassIntentionCelebrateInputSerializer,
    MassIntentionDeclineInputSerializer,
    MassIntentionOutputSerializer,
    MassIntentionProposeDateInputSerializer,
    MassIntentionReceiptOutputSerializer,
    MassIntentionSubmitInputSerializer,
)
from .services import (
    mass_intention_accept,
    mass_intention_celebrate,
    mass_intention_confirm_date,
    mass_intention_decline,
    mass_intention_propose_date,
    mass_intention_receipt_ensure,
    mass_intention_submit,
)

# Alias historique — la définition vit dans selectors.py, pour que la garde de
# rôle ci-dessous et la garde de périmètre territorial partagent une seule source.
CLERGY_ROLES = CLERGY_PASTORAL_ROLES


def _error(exc: ApplicationError) -> Response:
    return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)


class MassIntentionSubmitApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsOnboardingCompleted]  # A1 — écriture territoriale

    @extend_schema(
        request=MassIntentionSubmitInputSerializer,
        responses={201: MassIntentionOutputSerializer},
        tags=["mass-intentions"],
        summary="Soumettre une intention de messe",
    )
    def post(self, request):
        serializer = MassIntentionSubmitInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        parish = None
        if data.get("parish_id"):
            from apps.org.models import Parish

            try:
                parish = Parish.objects.get(id=data["parish_id"])
            except Parish.DoesNotExist:
                return Response(
                    {"detail": "Paroisse introuvable."}, status=status.HTTP_400_BAD_REQUEST
                )
        try:
            intention = mass_intention_submit(
                requestor=request.user,
                intention_type=data["intention_type"],
                intention_text=data["intention_text"],
                parish=parish,
            )
        except ApplicationError as e:
            return _error(e)
        return Response(
            MassIntentionOutputSerializer(intention).data, status=status.HTTP_201_CREATED
        )


class MassIntentionMyListApi(ApiAuthMixin, APIView):
    @extend_schema(
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT),
            OpenApiParameter("offset", OpenApiTypes.INT),
        ],
        responses={200: MassIntentionOutputSerializer(many=True)},
        tags=["mass-intentions"],
        summary="Mes intentions de messe (fidèle)",
    )
    def get(self, request):
        intentions = mass_intention_list_for_requestor(requestor=request.user)
        return get_paginated_response(
            pagination_class=LimitOffsetPagination,
            serializer_class=MassIntentionOutputSerializer,
            queryset=intentions,
            request=request,
            view=self,
        )


class MassIntentionParishListApi(ApiAuthMixin, APIView):
    @extend_schema(
        parameters=[
            OpenApiParameter("limit", OpenApiTypes.INT),
            OpenApiParameter("offset", OpenApiTypes.INT),
        ],
        responses={200: MassIntentionOutputSerializer(many=True)},
        tags=["mass-intentions"],
        summary="Intentions de la paroisse (prêtre)",
    )
    def get(self, request):
        if getattr(request.user, "pastoral_role", None) not in CLERGY_ROLES:
            return Response(
                {"detail": "Accès réservé au clergé."},
                status=status.HTTP_403_FORBIDDEN,
            )
        intentions = mass_intention_list_pending(pretre=request.user)
        return get_paginated_response(
            pagination_class=LimitOffsetPagination,
            serializer_class=MassIntentionOutputSerializer,
            queryset=intentions,
            request=request,
            view=self,
        )


class MassIntentionAcceptApi(ApiAuthMixin, APIView):
    @extend_schema(
        request=None,
        responses={200: MassIntentionOutputSerializer},
        tags=["mass-intentions"],
        summary="Accepter une intention de messe",
    )
    def post(self, request, intention_id: int):
        if getattr(request.user, "pastoral_role", None) not in CLERGY_ROLES:
            return Response(
                {"detail": "Accès réservé au clergé."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            intention = mass_intention_get(intention_id=intention_id, user=request.user)
            intention = mass_intention_accept(intention=intention, pretre=request.user)
        except ApplicationError as e:
            return _error(e)
        return Response(MassIntentionOutputSerializer(intention).data)


class MassIntentionProposeDateApi(ApiAuthMixin, APIView):
    @extend_schema(
        request=MassIntentionProposeDateInputSerializer,
        responses={200: MassIntentionOutputSerializer},
        tags=["mass-intentions"],
        summary="Proposer une date de célébration",
    )
    def post(self, request, intention_id: int):
        if getattr(request.user, "pastoral_role", None) not in CLERGY_ROLES:
            return Response(
                {"detail": "Accès réservé au clergé."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = MassIntentionProposeDateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            intention = mass_intention_get(intention_id=intention_id, user=request.user)
            intention = mass_intention_propose_date(
                intention=intention,
                proposed_date=serializer.validated_data["proposed_date"],
                pretre=request.user,
            )
        except ApplicationError as e:
            return _error(e)
        return Response(MassIntentionOutputSerializer(intention).data)


class MassIntentionConfirmDateApi(ApiAuthMixin, APIView):
    """``date_proposed → confirmed``.

    Volontairement **sans garde de rôle clergé** au niveau de la vue : c'est
    d'abord l'acte du fidèle demandeur, qui accepte la date qu'on lui propose.
    L'autorisation fine (demandeur, ou clergé de la paroisse) est portée par
    ``mass_intention_confirm_date`` — un seul endroit, valable aussi hors HTTP.
    La visibilité, elle, est déjà cloisonnée par ``mass_intention_get`` (404
    pour un tiers).
    """

    @extend_schema(
        request=None,
        responses={200: MassIntentionOutputSerializer},
        tags=["mass-intentions"],
        summary="Confirmer la date de célébration proposée",
        description=(
            "Confirme la date proposée par la paroisse. Réservé au fidèle "
            "demandeur ou à un membre du clergé ayant autorité sur la paroisse "
            "de l'intention. L'intention doit être au statut `date_proposed`."
        ),
    )
    def post(self, request, intention_id: int):
        try:
            intention = mass_intention_get(intention_id=intention_id, user=request.user)
            intention = mass_intention_confirm_date(intention=intention, user=request.user)
        except ApplicationError as e:
            return _error(e)
        return Response(MassIntentionOutputSerializer(intention).data)


class MassIntentionCelebrateApi(ApiAuthMixin, APIView):
    @extend_schema(
        request=MassIntentionCelebrateInputSerializer,
        responses={200: MassIntentionOutputSerializer},
        tags=["mass-intentions"],
        summary="Marquer une intention comme célébrée",
        description=(
            "Clôt le cycle et émet le reçu numérique. `celebration_date` est "
            "facultative : à défaut, la date confirmée ou proposée est retenue, "
            "sinon la date du jour."
        ),
    )
    def post(self, request, intention_id: int):
        if getattr(request.user, "pastoral_role", None) not in CLERGY_ROLES:
            return Response(
                {"detail": "Accès réservé au clergé."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = MassIntentionCelebrateInputSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        try:
            intention = mass_intention_get(intention_id=intention_id, user=request.user)
            intention = mass_intention_celebrate(
                intention=intention,
                pretre=request.user,
                celebration_date=serializer.validated_data.get("celebration_date"),
            )
        except ApplicationError as e:
            return _error(e)
        return Response(MassIntentionOutputSerializer(intention).data)


class MassIntentionReceiptApi(ApiAuthMixin, APIView):
    """Reçu numérique — **rejouable**.

    ``GET`` plutôt que ``POST`` parce que côté client c'est un téléchargement :
    le fidèle revient chercher sa trace, éventuellement des mois plus tard. La
    génération éventuelle reste dans le service (``mass_intention_receipt_ensure``)
    et n'a lieu que si le fichier manque — un reçu déjà émis est renvoyé tel
    quel, jamais réécrit. Aucune donnée du client n'entre dans le PDF.

    Pas de garde de rôle ici : ``mass_intention_get`` limite déjà l'accès au
    demandeur et au clergé territorialement compétent (404 sinon).
    """

    @extend_schema(
        responses={200: MassIntentionReceiptOutputSerializer},
        tags=["mass-intentions"],
        summary="Récupérer le reçu numérique d'une intention célébrée",
        description=(
            "Renvoie l'URL du reçu PDF. Disponible uniquement pour une "
            "intention au statut `celebrated`."
        ),
    )
    def get(self, request, intention_id: int):
        try:
            intention = mass_intention_get(intention_id=intention_id, user=request.user)
            intention = mass_intention_receipt_ensure(intention=intention)
        except ApplicationError as e:
            return _error(e)
        receipt = intention.receipt_file
        return Response(
            MassIntentionReceiptOutputSerializer(
                {
                    "reference": intention.reference,
                    "receipt_url": receipt.url if receipt and receipt.file else None,
                    "celebration_date": intention.celebration_date,
                }
            ).data
        )


class MassIntentionDeclineApi(ApiAuthMixin, APIView):
    @extend_schema(
        request=MassIntentionDeclineInputSerializer,
        responses={200: MassIntentionOutputSerializer},
        tags=["mass-intentions"],
        summary="Refuser une intention de messe",
    )
    def post(self, request, intention_id: int):
        if getattr(request.user, "pastoral_role", None) not in CLERGY_ROLES:
            return Response(
                {"detail": "Accès réservé au clergé."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = MassIntentionDeclineInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            intention = mass_intention_get(intention_id=intention_id, user=request.user)
            intention = mass_intention_decline(
                intention=intention,
                pretre=request.user,
                notes=serializer.validated_data.get("notes", ""),
            )
        except ApplicationError as e:
            return _error(e)
        return Response(MassIntentionOutputSerializer(intention).data)

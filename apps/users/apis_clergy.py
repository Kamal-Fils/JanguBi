"""APIs de la chaîne de validation des comptes clergé (auto-déclaration).

  GET  /api/v1/users/me/clergy-declaration/    Suivi de MA demande
  POST /api/v1/users/me/clergy-declaration/    Déposer une auto-déclaration
  GET  /api/v1/users/pending-validation/       File d'attente scopée au périmètre
  POST /api/v1/users/{id}/validate-account/    Approuver
  POST /api/v1/users/{id}/reject-account/      Refuser (motif obligatoire)

Couche HTTP uniquement : la file est produite par ``selectors``, les décisions
par ``services_clergy`` (qui portent le cloisonnement territorial fail-closed).
"""

from django.http import Http404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.mixins import ApiAuthMixin
from apps.api.pagination import LimitOffsetPagination, get_paginated_response
from apps.api.serializers import ErrorResponseSerializer
from apps.core.exceptions import ApplicationError
from apps.users.enums import CLERGY_PASTORAL_ROLES
from apps.users.models import ClergySelfDeclaration
from apps.users.permissions import IsClergyValidator, IsFidele
from apps.users.selectors import (
    clergy_declaration_current,
    clergy_pending_validation_list,
    user_get,
)
from apps.users.services_clergy import (
    clergy_declaration_submit,
    user_reject_clergy_account,
    user_validate_clergy_account,
)


def _get_ip(request) -> str | None:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _pending_declaration(obj) -> ClergySelfDeclaration | None:
    """Demande en attente préchargée par le selector (``to_attr``)."""
    declarations = getattr(obj, "pending_declarations", None)
    return declarations[0] if declarations else None


class PendingClergyItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    pastoral_role = serializers.SerializerMethodField()
    first_name = serializers.SerializerMethodField()
    last_name = serializers.SerializerMethodField()
    diocese_name = serializers.SerializerMethodField()
    parish_name = serializers.SerializerMethodField()
    date_joined = serializers.SerializerMethodField()
    # Ajouts non-cassants : le validateur ne peut pas trancher à l'aveugle, il lui
    # faut la pièce justificative et le mot du demandeur.
    justification_file_url = serializers.SerializerMethodField()
    declaration_message = serializers.SerializerMethodField()
    submitted_at = serializers.SerializerMethodField()

    def get_pastoral_role(self, obj) -> str | None:
        # Le rôle affiché est celui REVENDIQUÉ dans la demande. ``user.pastoral_role``
        # est encore laïc à ce stade, par conception (cf. ClergySelfDeclaration).
        declaration = _pending_declaration(obj)
        return declaration.claimed_pastoral_role if declaration else None

    def get_first_name(self, obj) -> str | None:
        profile = getattr(obj, "profile", None)
        return profile.first_name if profile else None

    def get_last_name(self, obj) -> str | None:
        profile = getattr(obj, "profile", None)
        return profile.last_name if profile else None

    def get_diocese_name(self, obj) -> str | None:
        declaration = _pending_declaration(obj)
        if declaration is not None and declaration.parish.diocese_id:
            return declaration.parish.diocese.name
        return obj.diocese.name if obj.diocese_id else None

    def get_parish_name(self, obj) -> str | None:
        declaration = _pending_declaration(obj)
        if declaration is not None:
            return declaration.parish.name
        profile = getattr(obj, "profile", None)
        if profile is None or not profile.primary_parish_id:
            return None
        return profile.primary_parish.name

    def get_date_joined(self, obj) -> str | None:
        return obj.created_at.isoformat() if obj.created_at else None

    def get_justification_file_url(self, obj) -> str | None:
        declaration = _pending_declaration(obj)
        if declaration is None:
            return None
        try:
            return declaration.justification_file.url
        except ValueError:
            # Fichier sans contenu attaché : on n'expose pas d'URL cassée.
            return None

    def get_declaration_message(self, obj) -> str:
        declaration = _pending_declaration(obj)
        return declaration.message if declaration else ""

    def get_submitted_at(self, obj) -> str | None:
        declaration = _pending_declaration(obj)
        return declaration.created_at.isoformat() if declaration else None


class PendingClergyPaginatedResponseSerializer(serializers.Serializer):
    limit = serializers.IntegerField()
    offset = serializers.IntegerField()
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = PendingClergyItemSerializer(many=True)


class ClergyDecisionOutputSerializer(serializers.Serializer):
    detail = serializers.CharField()
    id = serializers.UUIDField()
    clergy_validation_status = serializers.CharField()


class ClergyDeclarationOutputSerializer(serializers.Serializer):
    """État de MA demande — ce que le demandeur suit dans l'application."""

    id = serializers.IntegerField()
    claimed_pastoral_role = serializers.CharField()
    status = serializers.CharField()
    parish_id = serializers.IntegerField()
    parish_name = serializers.CharField(allow_null=True)
    message = serializers.CharField(allow_blank=True)
    rejection_reason = serializers.CharField(allow_blank=True)
    justification_file_url = serializers.CharField(allow_null=True)
    submitted_at = serializers.CharField(allow_null=True)
    reviewed_at = serializers.CharField(allow_null=True)


def _declaration_payload(declaration: ClergySelfDeclaration) -> dict:
    try:
        file_url = declaration.justification_file.url
    except ValueError:
        file_url = None
    return {
        "id": declaration.id,
        "claimed_pastoral_role": declaration.claimed_pastoral_role,
        "status": declaration.status,
        "parish_id": declaration.parish_id,
        "parish_name": declaration.parish.name,
        "message": declaration.message,
        # Le motif de refus est restitué au demandeur : sans lui, un refus est une
        # impasse — il ne peut ni comprendre ni corriger avant de resoumettre.
        "rejection_reason": declaration.rejection_reason,
        "justification_file_url": file_url,
        "submitted_at": declaration.created_at.isoformat() if declaration.created_at else None,
        "reviewed_at": declaration.reviewed_at.isoformat() if declaration.reviewed_at else None,
    }


class ClergyDeclarationCreateInputSerializer(serializers.Serializer):
    """Corps de la demande d'auto-déclaration.

    Déclaré au niveau module, et NON imbriqué dans la vue : drf-spectacular nomme
    le composant OpenAPI d'après la classe, donc une classe imbriquée
    ``InputSerializer`` produit un composant générique ``Input`` — déjà occupé par
    un tout autre endpoint (``{file_id}``). Le client qui dériverait son payload
    de ce nom se retrouverait typé sur la mauvaise forme : exactement la dérive
    de contrat silencieuse que ce projet a déjà payée.
    """

    claimed_pastoral_role = serializers.ChoiceField(
        choices=[(r, r) for r in sorted(CLERGY_PASTORAL_ROLES)],
        help_text="Rôle pastoral revendiqué (sans effet avant approbation).",
    )
    parish_id = serializers.IntegerField(
        min_value=1, help_text="Paroisse de rattachement revendiquée."
    )
    justification_file_id = serializers.IntegerField(
        min_value=1,
        help_text="ID du fichier justificatif téléversé via /v1/files/upload/standard/.",
    )
    message = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=2000,
        trim_whitespace=True,
        help_text="Précisions facultatives pour l'autorité validante.",
    )


class ClergyDeclarationMeApi(ApiAuthMixin, APIView):
    """Auto-déclaration de clergé — côté demandeur."""

    permission_classes = [IsFidele]

    InputSerializer = ClergyDeclarationCreateInputSerializer

    @extend_schema(
        tags=["Users"],
        summary="Consulter ma demande de compte clergé",
        description=(
            "Renvoie la dernière auto-déclaration du compte connecté (en attente, "
            "approuvée, ou refusée avec son motif), ou `null` si aucune demande "
            "n'a jamais été déposée."
        ),
        request=None,
        responses={
            200: ClergyDeclarationOutputSerializer,
            401: ErrorResponseSerializer,
        },
    )
    def get(self, request):
        declaration = clergy_declaration_current(user=request.user)
        if declaration is None:
            return Response(None)
        return Response(
            ClergyDeclarationOutputSerializer(_declaration_payload(declaration)).data
        )

    @extend_schema(
        tags=["Users"],
        summary="Déposer une auto-déclaration de compte clergé",
        description=(
            "Revendique un rôle pastoral, en joignant un justificatif et un "
            "territoire de rattachement. Le compte entre en file d'attente : la "
            "revendication n'accorde **aucun droit** tant que l'autorité "
            "compétente ne l'a pas approuvée. Une seule demande peut être en "
            "cours à la fois ; après un refus, une nouvelle demande est possible."
        ),
        request=InputSerializer,
        responses={
            201: ClergyDeclarationOutputSerializer,
            400: ErrorResponseSerializer,
            401: ErrorResponseSerializer,
        },
    )
    def post(self, request):
        s = self.InputSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        try:
            declaration = clergy_declaration_submit(
                user=request.user,
                ip=_get_ip(request),
                **s.validated_data,
            )
        except ApplicationError as exc:
            return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            ClergyDeclarationOutputSerializer(_declaration_payload(declaration)).data,
            status=status.HTTP_201_CREATED,
        )


class PendingClergyListApi(ApiAuthMixin, APIView):
    permission_classes = [IsClergyValidator]

    class Pagination(LimitOffsetPagination):
        default_limit = 50

    @extend_schema(
        tags=["Admin"],
        summary="Lister les comptes clergé en attente de validation",
        description=(
            "File d'attente des auto-déclarations clergé, restreinte au périmètre "
            "territorial de l'appelant (fail-closed : sans affectation territoriale, "
            "un validateur non global ne voit aucun dossier). Les comptes créés par "
            "invitation n'apparaissent jamais ici — accepter l'invitation vaut validation."
        ),
        request=None,  # GET : aucun corps de requête lu.
        parameters=[
            OpenApiParameter("limit", int, description="Nombre d'éléments par page (défaut 50)"),
            OpenApiParameter("offset", int, description="Index de début"),
        ],
        responses={
            200: PendingClergyPaginatedResponseSerializer,
            401: ErrorResponseSerializer,
            403: ErrorResponseSerializer,
        },
    )
    def get(self, request):
        pending = clergy_pending_validation_list(admin=request.user)
        return get_paginated_response(
            pagination_class=self.Pagination,
            serializer_class=PendingClergyItemSerializer,
            queryset=pending,
            request=request,
            view=self,
        )


class ClergyAccountValidateApi(ApiAuthMixin, APIView):
    permission_classes = [IsClergyValidator]

    @extend_schema(
        tags=["Admin"],
        summary="Valider un compte clergé en attente",
        description=(
            "Approuve une auto-déclaration clergé : le compte devient actif et vérifié. "
            "Réservé au super_admin (tous rôles) et à l'évêque/archevêque pour le clergé "
            "de son propre périmètre (prêtre, diacre, religieux)."
        ),
        request=None,  # Aucun corps requis : l'utilisateur cible est dans l'URL.
        responses={
            200: ClergyDecisionOutputSerializer,
            400: ErrorResponseSerializer,
            401: ErrorResponseSerializer,
            403: ErrorResponseSerializer,
            404: ErrorResponseSerializer,
        },
    )
    def post(self, request, user_id):
        user = user_get(user_id)
        if user is None:
            raise Http404

        try:
            user = user_validate_clergy_account(
                user=user,
                performed_by=request.user,
                ip=_get_ip(request),
            )
        except ApplicationError as exc:
            return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            ClergyDecisionOutputSerializer(
                {
                    "detail": "Compte clergé validé.",
                    "id": user.id,
                    "clergy_validation_status": user.clergy_validation_status,
                }
            ).data
        )


class ClergyAccountRejectInputSerializer(serializers.Serializer):
    """Motif de refus. Nommée au niveau module pour la même raison que
    ``ClergyDeclarationCreateInputSerializer`` : une classe imbriquée
    ``InputSerializer`` collisionne sur le composant OpenAPI générique ``Input``,
    et le client ne peut alors plus dériver son payload du contrat."""

    reason = serializers.CharField(max_length=500, allow_blank=False, trim_whitespace=True)


class ClergyAccountRejectApi(ApiAuthMixin, APIView):
    permission_classes = [IsClergyValidator]

    InputSerializer = ClergyAccountRejectInputSerializer

    @extend_schema(
        tags=["Admin"],
        summary="Refuser un compte clergé en attente",
        description=(
            "Refuse une auto-déclaration clergé. Le motif est obligatoire et notifié "
            "au demandeur par email. Le rôle pastoral revendiqué est retiré : le compte "
            "redevient un compte fidèle ordinaire."
        ),
        request=InputSerializer,
        responses={
            200: ClergyDecisionOutputSerializer,
            400: ErrorResponseSerializer,
            401: ErrorResponseSerializer,
            403: ErrorResponseSerializer,
            404: ErrorResponseSerializer,
        },
    )
    def post(self, request, user_id):
        user = user_get(user_id)
        if user is None:
            raise Http404

        s = self.InputSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        try:
            user = user_reject_clergy_account(
                user=user,
                reason=s.validated_data["reason"],
                performed_by=request.user,
                ip=_get_ip(request),
            )
        except ApplicationError as exc:
            return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            ClergyDecisionOutputSerializer(
                {
                    "detail": "Demande de compte clergé refusée.",
                    "id": user.id,
                    "clergy_validation_status": user.clergy_validation_status,
                }
            ).data
        )

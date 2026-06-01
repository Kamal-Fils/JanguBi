"""API de gestion des affectations de rôle scopées (RoleAssignment)."""

from django.db.models import Q
from drf_spectacular.openapi import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.mixins import ApiAuthMixin
from apps.core.exceptions import ApplicationError
from apps.org.models import Church, Diocese, Parish, Province
from apps.users.enums import RoleScope, UserRole
from apps.users.models import BaseUser, RoleAssignment
from apps.users.scoping import (
    accessible_diocese_ids,
    accessible_parish_ids,
    accessible_province_ids,
    is_global_admin,
    role_assignment_list,
    user_can_admin_diocese,
    user_can_admin_parish,
    user_can_admin_province,
)
from apps.users.services_roles import role_assignment_create, role_assignment_revoke


def _error(exc: ApplicationError) -> Response:
    return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)


def _forbidden() -> Response:
    return Response(
        {"detail": "Action hors de votre périmètre d'administration."},
        status=status.HTTP_403_FORBIDDEN,
    )


def _not_found(label: str) -> Response:
    return Response({"detail": f"{label} introuvable."}, status=status.HTTP_404_NOT_FOUND)


def _can_manage_assignment(user, ra: RoleAssignment) -> bool:
    if is_global_admin(user):
        return True
    if ra.scope == RoleScope.PARISH and ra.parish_id:
        return user_can_admin_parish(user, ra.parish_id)
    if ra.scope == RoleScope.CHURCH and ra.church_id:
        return user_can_admin_parish(user, ra.church.parish_id)
    if ra.scope == RoleScope.DIOCESE and ra.diocese_id:
        return user_can_admin_diocese(user, ra.diocese_id)
    if ra.scope == RoleScope.PROVINCE and ra.province_id:
        return user_can_admin_province(user, ra.province_id)
    return False


class RoleAssignmentOutputSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    scope_target_id = serializers.SerializerMethodField()

    class Meta:
        model = RoleAssignment
        fields = [
            "id", "user", "user_email", "role", "scope",
            "province", "diocese", "parish", "church", "scope_target_id",
            "is_principal", "is_active", "start_date", "end_date", "note", "created_at",
        ]

    def get_scope_target_id(self, obj) -> int | None:
        return obj.scope_target_id


class RoleAssignmentCreateInputSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    role = serializers.ChoiceField(choices=UserRole.choices)
    scope = serializers.ChoiceField(choices=RoleScope.choices)
    province_id = serializers.IntegerField(required=False, allow_null=True)
    diocese_id = serializers.IntegerField(required=False, allow_null=True)
    parish_id = serializers.IntegerField(required=False, allow_null=True)
    church_id = serializers.IntegerField(required=False, allow_null=True)
    is_principal = serializers.BooleanField(default=False)
    note = serializers.CharField(required=False, allow_blank=True, default="")


class RoleAssignmentListApi(ApiAuthMixin, APIView):
    @extend_schema(
        parameters=[OpenApiParameter("user", OpenApiTypes.UUID, description="Filtrer par utilisateur")],
        responses={200: RoleAssignmentOutputSerializer(many=True)},
        tags=["users"],
        summary="Lister les affectations de rôle (scopé au périmètre de l'appelant)",
    )
    def get(self, request):
        user_id = request.query_params.get("user")
        target = BaseUser.objects.filter(id=user_id).first() if user_id else None
        qs = role_assignment_list(user=target)

        if not is_global_admin(request.user):
            pids = accessible_parish_ids(request.user) or set()
            dids = accessible_diocese_ids(request.user) or set()
            prov = accessible_province_ids(request.user) or set()
            qs = qs.filter(
                Q(user=request.user)
                | Q(parish_id__in=pids)
                | Q(diocese_id__in=dids)
                | Q(province_id__in=prov)
            )
        return Response(RoleAssignmentOutputSerializer(qs, many=True).data)

    @extend_schema(
        request=RoleAssignmentCreateInputSerializer,
        responses={201: RoleAssignmentOutputSerializer},
        tags=["users"],
        summary="Attribuer un rôle scopé à un utilisateur (dans son propre périmètre)",
    )
    def post(self, request):
        serializer = RoleAssignmentCreateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        target = BaseUser.objects.filter(id=data["user_id"]).first()
        if target is None:
            return _not_found("Utilisateur")

        scope = data["scope"]
        province = diocese = parish = church = None

        if scope == RoleScope.GLOBAL:
            if not is_global_admin(request.user):
                return _forbidden()
        elif scope == RoleScope.PROVINCE:
            province = Province.objects.filter(id=data.get("province_id")).first()
            if province is None:
                return _not_found("Province")
            if not user_can_admin_province(request.user, province.id):
                return _forbidden()
        elif scope == RoleScope.DIOCESE:
            diocese = Diocese.objects.filter(id=data.get("diocese_id")).first()
            if diocese is None:
                return _not_found("Diocèse")
            if not user_can_admin_diocese(request.user, diocese.id):
                return _forbidden()
        elif scope == RoleScope.PARISH:
            parish = Parish.objects.filter(id=data.get("parish_id")).first()
            if parish is None:
                return _not_found("Paroisse")
            if not user_can_admin_parish(request.user, parish.id):
                return _forbidden()
        elif scope == RoleScope.CHURCH:
            church = Church.objects.select_related("parish").filter(id=data.get("church_id")).first()
            if church is None:
                return _not_found("Église")
            if not user_can_admin_parish(request.user, church.parish_id):
                return _forbidden()

        try:
            ra = role_assignment_create(
                user=target,
                role=data["role"],
                scope=scope,
                province=province,
                diocese=diocese,
                parish=parish,
                church=church,
                is_principal=data.get("is_principal", False),
                granted_by=request.user,
                note=data.get("note", ""),
            )
        except ApplicationError as e:
            return _error(e)
        return Response(RoleAssignmentOutputSerializer(ra).data, status=status.HTTP_201_CREATED)


class RoleAssignmentRevokeApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: RoleAssignmentOutputSerializer},
        tags=["users"],
        summary="Révoquer une affectation de rôle",
    )
    def post(self, request, assignment_id: int):
        ra = RoleAssignment.objects.select_related("church").filter(id=assignment_id).first()
        if ra is None:
            return _not_found("Affectation")
        if not _can_manage_assignment(request.user, ra):
            return _forbidden()
        ra = role_assignment_revoke(role_assignment=ra)
        return Response(RoleAssignmentOutputSerializer(ra).data)

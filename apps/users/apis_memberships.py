"""API des appartenances ecclésiales de l'utilisateur courant (Membership).

Endpoints /me/memberships/ — un utilisateur ne gère QUE ses propres appartenances.
PAS de garde IsOnboardingCompleted ici : c'est précisément le moyen DE compléter
l'onboarding (cf. Chantier 2).
"""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.mixins import ApiAuthMixin
from apps.core.exceptions import ApplicationError
from apps.users.scoping import org_church_get
from apps.users.selectors import (
    membership_get,
    membership_list_by_ids,
    membership_ref,
)
from apps.users.serializers import MembershipMeSerializer
from apps.users.services_memberships import (
    membership_create,
    membership_remove,
    membership_set_primary,
    memberships_create_batch,
)


def _error(exc: ApplicationError) -> Response:
    return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)


def _get_own_membership_or_response(request, membership_id: int):
    """Renvoie (membership, None) si l'appelant en est propriétaire, sinon
    (None, Response) avec 404 (inexistante) ou 403 (appartient à un autre)."""
    membership = membership_get(membership_id=membership_id)
    if membership is None:
        return None, Response(
            {"detail": "Appartenance introuvable."}, status=status.HTTP_404_NOT_FOUND
        )
    if membership.user_id != request.user.id:
        return None, Response(
            {"detail": "Cette appartenance ne vous appartient pas."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return membership, None


class MembershipCreateInputSerializer(serializers.Serializer):
    church_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=False,
        help_text="Lot d'IDs d'églises (cascade onboarding). La 1re devient principale.",
    )
    church_id = serializers.IntegerField(
        required=False, help_text="ID d'une seule église."
    )
    is_primary = serializers.BooleanField(required=False, default=False)

    def validate_church_ids(self, value):
        # Sans dédup, un doublon violerait unique_membership_user_church → 500.
        if len(value) != len(set(value)):
            raise serializers.ValidationError("La liste contient des églises en double.")
        return value

    def validate(self, attrs):
        if not attrs.get("church_ids") and not attrs.get("church_id"):
            raise serializers.ValidationError("Fournir 'church_ids' (lot) ou 'church_id'.")
        if attrs.get("church_ids") and attrs.get("church_id"):
            raise serializers.ValidationError(
                "Fournir 'church_ids' OU 'church_id', pas les deux."
            )
        return attrs


class MembershipMeListCreateApi(ApiAuthMixin, APIView):
    @extend_schema(
        request=MembershipCreateInputSerializer,
        responses={201: MembershipMeSerializer(many=True)},
        tags=["users"],
        summary="Ajouter une ou plusieurs appartenances (onboarding « set d'églises »)",
    )
    def post(self, request):
        s = MembershipCreateInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        try:
            if data.get("church_ids"):
                created = memberships_create_batch(
                    user=request.user, church_ids=data["church_ids"]
                )
            else:
                church = org_church_get(church_id=data["church_id"])
                if church is None:
                    raise ApplicationError(f"Église {data['church_id']} introuvable.")
                created = [
                    membership_create(
                        user=request.user,
                        church=church,
                        is_primary=data.get("is_primary", False),
                    )
                ]
        except ApplicationError as e:
            return _error(e)

        # Les objets renvoyés par membership_create n'ont pas la chaîne territoriale
        # préchargée → on recharge en une requête pour éviter le N+1 dans membership_ref.
        reloaded = membership_list_by_ids(membership_ids=[m.pk for m in created])
        payload = [membership_ref(m) for m in reloaded]
        return Response(
            MembershipMeSerializer(payload, many=True).data, status=status.HTTP_201_CREATED
        )


class MembershipMeDeleteApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={204: None},
        tags=["users"],
        summary="Retirer une de mes appartenances",
    )
    def delete(self, request, membership_id: int):
        membership, error = _get_own_membership_or_response(request, membership_id)
        if error is not None:
            return error
        try:
            membership_remove(user=request.user, membership=membership)
        except ApplicationError as e:
            return _error(e)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MembershipMeSetPrimaryApi(ApiAuthMixin, APIView):
    @extend_schema(
        request=None,
        responses={200: MembershipMeSerializer},
        tags=["users"],
        summary="Définir une de mes appartenances comme principale",
    )
    def patch(self, request, membership_id: int):
        membership, error = _get_own_membership_or_response(request, membership_id)
        if error is not None:
            return error
        try:
            membership = membership_set_primary(user=request.user, membership=membership)
        except ApplicationError as e:
            return _error(e)
        return Response(MembershipMeSerializer(membership_ref(membership)).data)

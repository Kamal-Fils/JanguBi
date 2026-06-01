from rest_framework import serializers

from apps.users.enums import PastoralRole

from .models import ClergicalInvitation

_INVITABLE_ROLES = [
    PastoralRole.PRETRE,
    PastoralRole.DIACRE,
    PastoralRole.RELIGIEUX,
    PastoralRole.EVEQUE,
    PastoralRole.ARCHEVEQUE,
]


class InvitationCreateInputSerializer(serializers.Serializer):
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    pastoral_role = serializers.ChoiceField(choices=[(r, r) for r in _INVITABLE_ROLES])
    diocese_id = serializers.IntegerField(required=False, allow_null=True)
    parish_id = serializers.IntegerField(
        required=False, allow_null=True, help_text="Paroisse cible (prêtre/diacre)."
    )
    church_id = serializers.IntegerField(
        required=False, allow_null=True, help_text="Église cible (diacre)."
    )


class InvitationOutputSerializer(serializers.ModelSerializer):
    diocese_name = serializers.CharField(source="diocese.name", read_only=True, default=None)
    created_by_name = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = ClergicalInvitation
        fields = [
            "id",
            "token",
            "email",
            "first_name",
            "last_name",
            "pastoral_role",
            "diocese_name",
            "status",
            "status_label",
            "created_by_name",
            "expires_at",
            "created_at",
        ]

    def get_created_by_name(self, obj: ClergicalInvitation) -> str | None:
        if not obj.created_by:
            return None
        try:
            profile = obj.created_by.profile
            name = f"{profile.first_name} {profile.last_name}".strip()
            return name or obj.created_by.email
        except Exception:
            return obj.created_by.email


class InvitationAcceptInputSerializer(serializers.Serializer):
    token = serializers.UUIDField()


class InvitationRevokeInputSerializer(serializers.Serializer):
    pass

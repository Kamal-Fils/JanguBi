from rest_framework import serializers

from apps.spiritual.models import PastoralReflection


class ReflectionOutputSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    scope_parish_id = serializers.IntegerField(read_only=True, allow_null=True)
    scope_diocese_id = serializers.IntegerField(read_only=True, allow_null=True)
    scope_church_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = PastoralReflection
        fields = [
            "id",
            "title",
            "content",
            "reflection_date",
            "scope_type",
            "scope_parish_id",
            "scope_diocese_id",
            "scope_church_id",
            "author_name",
            "created_at",
            "updated_at",
        ]

    def get_author_name(self, obj) -> str:
        profile = getattr(obj.author, "profile", None)
        if profile is not None:
            full = f"{profile.first_name} {profile.last_name}".strip()
            if full:
                return full
        return obj.author.email


class ReflectionUpsertInputSerializer(serializers.Serializer):
    content = serializers.CharField()
    reflection_date = serializers.DateField(required=False)
    title = serializers.CharField(required=False, allow_blank=True, default="")
    scope_type = serializers.ChoiceField(
        choices=PastoralReflection.ScopeType.choices,
        default=PastoralReflection.ScopeType.PARISH,
    )
    scope_parish_id = serializers.IntegerField(required=False, allow_null=True)
    scope_diocese_id = serializers.IntegerField(required=False, allow_null=True)
    scope_church_id = serializers.IntegerField(required=False, allow_null=True)

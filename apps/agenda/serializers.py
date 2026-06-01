from rest_framework import serializers


class EventInputSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    event_type = serializers.ChoiceField(choices=["mass", "conference", "retreat", "ordination", "other"])
    start_at = serializers.DateTimeField()
    end_at = serializers.DateTimeField()
    location = serializers.CharField(required=False, allow_blank=True, default="")
    scope_type = serializers.ChoiceField(
        choices=["global", "diocese", "parish", "church"],
        required=False,
        default="global",
    )
    # scope_id (legacy, désambiguïsé par scope_type pour parish/diocese) + scope_church_id.
    scope_id = serializers.IntegerField(required=False, allow_null=True)
    scope_church_id = serializers.IntegerField(required=False, allow_null=True)
    max_participants = serializers.IntegerField(required=False, allow_null=True, min_value=1)


class EventOutputSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    description = serializers.CharField()
    event_type = serializers.CharField()
    start_at = serializers.DateTimeField()
    end_at = serializers.DateTimeField()
    location = serializers.CharField()
    scope_type = serializers.CharField()
    # Back-compat : scope_id = l'id de la portée courante ; + ids FK explicites.
    scope_id = serializers.SerializerMethodField()
    scope_parish_id = serializers.IntegerField(allow_null=True)
    scope_diocese_id = serializers.IntegerField(allow_null=True)
    scope_church_id = serializers.IntegerField(allow_null=True)
    max_participants = serializers.IntegerField(allow_null=True)
    organizer_email = serializers.SerializerMethodField()
    registration_count = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()

    def get_scope_id(self, obj):
        return obj.scope_parish_id or obj.scope_diocese_id or obj.scope_church_id

    def get_organizer_email(self, obj):
        return obj.organizer.email if obj.organizer_id else None

    def get_registration_count(self, obj):
        if hasattr(obj, "registrations"):
            return obj.registrations.count()
        return 0


class RegistrationOutputSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    user_email = serializers.SerializerMethodField()
    registered_at = serializers.DateTimeField()

    def get_user_email(self, obj):
        return obj.user.email if obj.user_id else None

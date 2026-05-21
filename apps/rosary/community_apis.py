from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from apps.api.mixins import ApiAuthMixin
from apps.core.exceptions import ApplicationError


def _error(exc: ApplicationError) -> Response:
    return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)


class CommunityRosaryInputSerializer(serializers.Serializer):
    mystery_group_id = serializers.IntegerField(required=False, allow_null=True)
    intention = serializers.CharField(required=False, allow_blank=True, default="")


class IntentionInputSerializer(serializers.Serializer):
    text = serializers.CharField()


class CommunityRosaryOutputSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    initiator_email = serializers.SerializerMethodField()
    mystery_group_name = serializers.SerializerMethodField()
    intention = serializers.CharField()
    status = serializers.CharField()
    current_decade = serializers.IntegerField()
    started_at = serializers.DateTimeField()

    def get_initiator_email(self, obj):
        return obj.initiator.email if obj.initiator_id else None

    def get_mystery_group_name(self, obj):
        return obj.mystery_group.name if obj.mystery_group_id else None


class CommunityRosaryListCreateApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: CommunityRosaryOutputSerializer(many=True)},
        tags=["Chapelet"],
        summary="Liste des chapelets communautaires actifs",
    )
    def get(self, request):
        from apps.rosary.community_services import community_rosary_list_active

        sessions = community_rosary_list_active()
        return Response(CommunityRosaryOutputSerializer(sessions, many=True).data)

    @extend_schema(
        request=CommunityRosaryInputSerializer,
        responses={201: CommunityRosaryOutputSerializer},
        tags=["Chapelet"],
        summary="Initier un chapelet communautaire (clergé seulement)",
    )
    def post(self, request):
        from apps.rosary.community_services import community_rosary_start

        serializer = CommunityRosaryInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            session = community_rosary_start(initiator=request.user, **serializer.validated_data)
        except ApplicationError as e:
            return _error(e)
        return Response(CommunityRosaryOutputSerializer(session).data, status=status.HTTP_201_CREATED)


class CommunityRosaryJoinApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: CommunityRosaryOutputSerializer},
        tags=["Chapelet"],
        summary="Rejoindre un chapelet communautaire",
    )
    def post(self, request, rosary_id: int):
        from apps.rosary.community_services import community_rosary_get, community_rosary_join

        try:
            rosary = community_rosary_get(rosary_id=rosary_id)
            community_rosary_join(rosary=rosary, user=request.user)
        except ApplicationError as e:
            return _error(e)
        return Response(CommunityRosaryOutputSerializer(rosary).data)


class CommunityRosaryIntentionApi(ApiAuthMixin, APIView):
    @extend_schema(
        request=IntentionInputSerializer,
        responses={201: None},
        tags=["Chapelet"],
        summary="Soumettre une intention de prière",
    )
    def post(self, request, rosary_id: int):
        from apps.rosary.community_services import community_rosary_get, community_rosary_submit_intention

        serializer = IntentionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            rosary = community_rosary_get(rosary_id=rosary_id)
            community_rosary_submit_intention(
                rosary=rosary,
                user=request.user,
                text=serializer.validated_data["text"],
            )
        except ApplicationError as e:
            return _error(e)
        return Response(status=status.HTTP_201_CREATED)


class CommunityRosaryEndApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: CommunityRosaryOutputSerializer},
        tags=["Chapelet"],
        summary="Terminer un chapelet communautaire (initiateur seulement)",
    )
    def post(self, request, rosary_id: int):
        from apps.rosary.community_services import community_rosary_end, community_rosary_get

        try:
            rosary = community_rosary_get(rosary_id=rosary_id)
            rosary = community_rosary_end(rosary=rosary, user=request.user)
        except ApplicationError as e:
            return _error(e)
        return Response(CommunityRosaryOutputSerializer(rosary).data)

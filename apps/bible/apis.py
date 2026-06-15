from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.mixins import ApiAuthMixin
from apps.api.pagination import LimitOffsetPagination, get_paginated_response
from apps.core.exceptions import ApplicationError


def _error(exc: ApplicationError) -> Response:
    return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)


# ─── Serializers ──────────────────────────────────────────────────────────────

class HomilieNoteInputSerializer(serializers.Serializer):
    passage_start_id = serializers.IntegerField()
    passage_end_id = serializers.IntegerField(required=False, allow_null=True)
    content = serializers.CharField()


class HomilieNoteOutputSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    passage_start_id = serializers.IntegerField()
    passage_end_id = serializers.IntegerField(allow_null=True)
    content = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class LectioDivinaInputSerializer(serializers.Serializer):
    passage_id = serializers.IntegerField()
    lectio = serializers.CharField(allow_blank=True, default="")
    meditatio = serializers.CharField(allow_blank=True, default="")
    oratio = serializers.CharField(allow_blank=True, default="")
    contemplatio = serializers.CharField(allow_blank=True, default="")


class LectioDivinaOutputSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    passage_id = serializers.IntegerField()
    lectio = serializers.CharField()
    meditatio = serializers.CharField()
    oratio = serializers.CharField()
    contemplatio = serializers.CharField()
    updated_at = serializers.DateTimeField()


class ReadingPlanInputSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(allow_blank=True, default="")


class ReadingPlanOutputSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    description = serializers.CharField()
    is_published = serializers.BooleanField()
    author_email = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()

    def get_author_email(self, obj):
        return obj.author.email if obj.author_id else None


# ─── APIs ─────────────────────────────────────────────────────────────────────

class HomilieNoteListCreateApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: HomilieNoteOutputSerializer(many=True)},
        tags=["Bible — Avancé"],
        summary="List mes notes d'homélie",
    )
    def get(self, request):
        from apps.bible.selectors import homilenote_list

        notes = homilenote_list(author=request.user)
        return get_paginated_response(
            pagination_class=LimitOffsetPagination,
            serializer_class=HomilieNoteOutputSerializer,
            queryset=notes,
            request=request,
            view=self,
        )

    @extend_schema(
        request=HomilieNoteInputSerializer,
        responses={201: HomilieNoteOutputSerializer},
        tags=["Bible — Avancé"],
        summary="Créer une note d'homélie (DIACRE+)",
    )
    def post(self, request):
        from apps.bible.services.bible_advanced import homilenote_create

        serializer = HomilieNoteInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            note = homilenote_create(author=request.user, **serializer.validated_data)
        except ApplicationError as e:
            return _error(e)
        return Response(HomilieNoteOutputSerializer(note).data, status=status.HTTP_201_CREATED)


class HomilieNoteDetailApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: HomilieNoteOutputSerializer},
        tags=["Bible — Avancé"],
        summary="Récupérer une note d'homélie",
    )
    def get(self, request, note_id: int):
        from apps.bible.selectors import homilenote_get

        try:
            note = homilenote_get(note_id=note_id, user=request.user)
        except ApplicationError as e:
            return _error(e)
        return Response(HomilieNoteOutputSerializer(note).data)

    @extend_schema(
        request=HomilieNoteInputSerializer,
        responses={200: HomilieNoteOutputSerializer},
        tags=["Bible — Avancé"],
        summary="Modifier une note d'homélie",
    )
    def patch(self, request, note_id: int):
        from apps.bible.selectors import homilenote_get
        from apps.bible.services.bible_advanced import homilenote_update

        try:
            note = homilenote_get(note_id=note_id, user=request.user)
            note = homilenote_update(note=note, content=request.data.get("content", note.content))
        except ApplicationError as e:
            return _error(e)
        return Response(HomilieNoteOutputSerializer(note).data)

    @extend_schema(
        responses={204: None},
        tags=["Bible — Avancé"],
        summary="Supprimer une note d'homélie",
    )
    def delete(self, request, note_id: int):
        from apps.bible.selectors import homilenote_get
        from apps.bible.services.bible_advanced import homilenote_delete

        try:
            note = homilenote_get(note_id=note_id, user=request.user)
            homilenote_delete(note=note, user=request.user)
        except ApplicationError as e:
            return _error(e)
        return Response(status=status.HTTP_204_NO_CONTENT)


class LectioDivinaSessionApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: LectioDivinaOutputSerializer(many=True)},
        tags=["Bible — Avancé"],
        summary="Liste mes sessions Lectio Divina",
    )
    def get(self, request):
        from apps.bible.selectors import lectio_divina_list

        sessions = lectio_divina_list(user=request.user)
        return get_paginated_response(
            pagination_class=LimitOffsetPagination,
            serializer_class=LectioDivinaOutputSerializer,
            queryset=sessions,
            request=request,
            view=self,
        )

    @extend_schema(
        request=LectioDivinaInputSerializer,
        responses={200: LectioDivinaOutputSerializer},
        tags=["Bible — Avancé"],
        summary="Créer ou mettre à jour une session Lectio Divina",
    )
    def post(self, request):
        from apps.bible.services.bible_advanced import lectio_divina_upsert

        serializer = LectioDivinaInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            session = lectio_divina_upsert(user=request.user, **serializer.validated_data)
        except ApplicationError as e:
            return _error(e)
        return Response(LectioDivinaOutputSerializer(session).data)


class ReadingPlanListCreateApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: ReadingPlanOutputSerializer(many=True)},
        tags=["Bible — Avancé"],
        summary="Liste les plans de lecture publiés",
    )
    def get(self, request):
        from apps.bible.selectors import reading_plan_list

        plans = reading_plan_list(published_only=True)
        return get_paginated_response(
            pagination_class=LimitOffsetPagination,
            serializer_class=ReadingPlanOutputSerializer,
            queryset=plans,
            request=request,
            view=self,
        )

    @extend_schema(
        request=ReadingPlanInputSerializer,
        responses={201: ReadingPlanOutputSerializer},
        tags=["Bible — Avancé"],
        summary="Créer un plan de lecture (PRETRE+)",
    )
    def post(self, request):
        from apps.bible.services.bible_advanced import reading_plan_create

        serializer = ReadingPlanInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            plan = reading_plan_create(author=request.user, **serializer.validated_data)
        except ApplicationError as e:
            return _error(e)
        return Response(ReadingPlanOutputSerializer(plan).data, status=status.HTTP_201_CREATED)


class ReadingPlanDetailApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: ReadingPlanOutputSerializer},
        tags=["Bible — Avancé"],
        summary="Détail d'un plan de lecture",
    )
    def get(self, request, plan_id: int):
        from apps.bible.selectors import reading_plan_get

        try:
            plan = reading_plan_get(plan_id=plan_id)
        except ApplicationError as e:
            return _error(e)
        return Response(ReadingPlanOutputSerializer(plan).data)

    @extend_schema(
        responses={200: ReadingPlanOutputSerializer},
        tags=["Bible — Avancé"],
        summary="Publier un plan de lecture",
    )
    def post(self, request, plan_id: int):
        from apps.bible.selectors import reading_plan_get
        from apps.bible.services.bible_advanced import reading_plan_publish

        try:
            plan = reading_plan_get(plan_id=plan_id)
            plan = reading_plan_publish(plan=plan, user=request.user)
        except ApplicationError as e:
            return _error(e)
        return Response(ReadingPlanOutputSerializer(plan).data)

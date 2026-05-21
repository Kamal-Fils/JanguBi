from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.openapi import OpenApiTypes

from apps.api.mixins import ApiAuthMixin
from apps.api.pagination import LimitOffsetPagination, get_paginated_response
from apps.core.exceptions import ApplicationError

from apps.agenda.serializers import (
    EventInputSerializer,
    EventOutputSerializer,
    RegistrationOutputSerializer,
)


def _error(exc: ApplicationError) -> Response:
    return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)


class EventListCreateApi(ApiAuthMixin, APIView):
    @extend_schema(
        parameters=[
            OpenApiParameter("scope_type", OpenApiTypes.STR, description="Filter by scope (global/diocese/parish)"),
            OpenApiParameter("event_type", OpenApiTypes.STR, description="Filter by event type"),
            OpenApiParameter("upcoming_only", OpenApiTypes.BOOL, description="Only future events (default true)"),
            OpenApiParameter("limit", OpenApiTypes.INT),
            OpenApiParameter("offset", OpenApiTypes.INT),
        ],
        responses={200: EventOutputSerializer(many=True)},
        tags=["Agenda"],
        summary="Liste des événements",
    )
    def get(self, request):
        from apps.agenda.selectors import event_list

        scope_type = request.query_params.get("scope_type")
        event_type = request.query_params.get("event_type")
        upcoming_only = request.query_params.get("upcoming_only", "true").lower() != "false"
        events = event_list(scope_type=scope_type, event_type=event_type, upcoming_only=upcoming_only)
        return get_paginated_response(
            pagination_class=LimitOffsetPagination,
            serializer_class=EventOutputSerializer,
            queryset=events,
            request=request,
            view=self,
        )

    @extend_schema(
        request=EventInputSerializer,
        responses={201: EventOutputSerializer},
        tags=["Agenda"],
        summary="Créer un événement (clergé ou admin)",
    )
    def post(self, request):
        from apps.agenda.services import event_create

        serializer = EventInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            event = event_create(organizer=request.user, **serializer.validated_data)
        except ApplicationError as e:
            return _error(e)
        return Response(EventOutputSerializer(event).data, status=status.HTTP_201_CREATED)


class EventDetailApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: EventOutputSerializer},
        tags=["Agenda"],
        summary="Détail d'un événement",
    )
    def get(self, request, event_id: int):
        from apps.agenda.selectors import event_get

        try:
            event = event_get(event_id=event_id)
        except ApplicationError as e:
            return _error(e)
        return Response(EventOutputSerializer(event).data)


class EventRegisterApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={201: None},
        tags=["Agenda"],
        summary="S'inscrire à un événement",
    )
    def post(self, request, event_id: int):
        from apps.agenda.selectors import event_get
        from apps.agenda.services import event_register

        try:
            event = event_get(event_id=event_id)
            event_register(event=event, user=request.user)
        except ApplicationError as e:
            return _error(e)
        return Response(status=status.HTTP_201_CREATED)


class EventRegistrationsApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: RegistrationOutputSerializer(many=True)},
        tags=["Agenda"],
        summary="Liste des inscrits (clergé seulement)",
    )
    def get(self, request, event_id: int):
        from apps.agenda.selectors import event_registrations_list

        registrations = event_registrations_list(event_id=event_id)
        return get_paginated_response(
            pagination_class=LimitOffsetPagination,
            serializer_class=RegistrationOutputSerializer,
            queryset=registrations,
            request=request,
            view=self,
        )

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.openapi import OpenApiTypes

from apps.api.mixins import ApiAuthMixin
from apps.api.pagination import (
    LimitOffsetPagination,
    get_paginated_response,
    paginated_response_serializer,
)
from apps.core.exceptions import ApplicationError
from apps.users.permissions import IsOnboardingCompleted

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
            OpenApiParameter("event_type", OpenApiTypes.STR, description="Filter by event type"),
            OpenApiParameter("upcoming_only", OpenApiTypes.BOOL, description="Only future events (default true)"),
            OpenApiParameter("limit", OpenApiTypes.INT),
            OpenApiParameter("offset", OpenApiTypes.INT),
        ],
        responses={200: paginated_response_serializer(EventOutputSerializer)},
        tags=["Agenda"],
        summary="Liste des événements (scopée aux appartenances de l'utilisateur)",
    )
    def get(self, request):
        from apps.agenda.selectors import event_list_for_user

        event_type = request.query_params.get("event_type")
        upcoming_only = request.query_params.get("upcoming_only", "true").lower() != "false"
        events = event_list_for_user(
            user=request.user, event_type=event_type, upcoming_only=upcoming_only
        )
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
            event = event_get(event_id=event_id, user=request.user)
        except ApplicationError as e:
            return _error(e)
        return Response(EventOutputSerializer(event).data)


class EventRegisterApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsOnboardingCompleted]  # A1 — écriture territoriale

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

    @extend_schema(
        responses={204: None},
        tags=["Agenda"],
        summary="Annuler son inscription à un événement",
    )
    def delete(self, request, event_id: int):
        from apps.agenda.selectors import event_get
        from apps.agenda.services import event_unregister

        try:
            event = event_get(event_id=event_id)
            event_unregister(event=event, user=request.user)
        except ApplicationError as e:
            return _error(e)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _can_view_event_registrations(user, event) -> bool:
    """Liste des inscrits réservée : organisateur, admin global, ou autorité sur la
    portée de l'événement (église→sa paroisse, paroisse, diocèse). Ferme le trou
    où tout authentifié lisait la liste."""
    if event.organizer_id is not None and event.organizer_id == user.id:
        return True
    from apps.agenda.models import Event
    from apps.users.scoping import (
        is_global_admin,
        user_can_admin_church,
        user_can_admin_diocese,
        user_can_admin_parish,
    )

    if is_global_admin(user):
        return True
    if event.scope_type == Event.ScopeType.CHURCH and event.scope_church_id:
        return user_can_admin_church(user, event.scope_church_id)
    if event.scope_type == Event.ScopeType.PARISH and event.scope_parish_id:
        return user_can_admin_parish(user, event.scope_parish_id)
    if event.scope_type == Event.ScopeType.DIOCESE and event.scope_diocese_id:
        return user_can_admin_diocese(user, event.scope_diocese_id)
    return False


class EventRegistrationsApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: paginated_response_serializer(RegistrationOutputSerializer)},
        tags=["Agenda"],
        summary="Liste des inscrits (autorité sur la portée de l'événement)",
    )
    def get(self, request, event_id: int):
        from apps.agenda.selectors import event_get, event_registrations_list

        try:
            event = event_get(event_id=event_id)
        except ApplicationError as e:
            return _error(e)
        if not _can_view_event_registrations(request.user, event):
            return Response(
                {"detail": "Réservé au clergé/admin ayant autorité sur cet événement."},
                status=status.HTTP_403_FORBIDDEN,
            )

        registrations = event_registrations_list(event_id=event_id)
        return get_paginated_response(
            pagination_class=LimitOffsetPagination,
            serializer_class=RegistrationOutputSerializer,
            queryset=registrations,
            request=request,
            view=self,
        )

import datetime

from django.utils import timezone
from drf_spectacular.openapi import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.mixins import ApiAuthMixin
from apps.dashboards.analytics import donation_analytics, resolve_analytics_context
from apps.dashboards.selectors import (
    cure_dashboard,
    diocese_dashboard,
    fidele_dashboard,
    user_principal_diocese_id,
    user_principal_parish_id,
)
from apps.users.scoping import (
    accessible_diocese_ids,
    accessible_parish_ids,
    user_can_admin_diocese,
    user_can_admin_parish,
)


def _parse_period(request) -> tuple[datetime.datetime, datetime.datetime, str]:
    """Plage temporelle + granularité depuis les query params. Priorité à
    ``from``/``to`` ISO ; sinon un preset ``period`` (today/week/month/quarter/year)."""
    granularity = request.query_params.get("granularity", "month")
    now = timezone.now()

    frm, to = request.query_params.get("from"), request.query_params.get("to")
    if frm and to:
        try:
            since = datetime.datetime.fromisoformat(frm)
            until = datetime.datetime.fromisoformat(to)
            if timezone.is_naive(since):
                since = timezone.make_aware(since)
            if timezone.is_naive(until):
                until = timezone.make_aware(until)
            return since, until, granularity
        except ValueError:
            pass

    period = request.query_params.get("period", "year")
    if period == "today":
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
        granularity = "day"
    elif period == "week":
        since = now - datetime.timedelta(days=7)
        granularity = "day" if granularity == "month" else granularity
    elif period == "month":
        since = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "quarter":
        since = now - datetime.timedelta(days=90)
    else:  # year
        since = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return since, now, granularity


def _maybe_narrow(context: dict, request) -> dict:
    """Drill-down spatial : ``?parish=`` / ``?diocese=`` re-cadrent l'analyse sur
    une entité PLUS FINE, uniquement si elle est dans le périmètre autorisé."""
    from apps.org.models import Diocese, Parish

    user = request.user
    parish = request.query_params.get("parish")
    diocese = request.query_params.get("diocese")

    if parish:
        try:
            pid = int(parish)
        except ValueError:
            return context
        allowed = accessible_parish_ids(user)  # None = illimité (super_admin)
        if allowed is None or pid in allowed:
            p = Parish.objects.filter(id=pid).first()
            return {
                "level": "parish",
                "entity": {"id": p.id, "name": p.name} if p else None,
                "scope": {"parish_ids": [pid]},
            }
        return context

    if diocese:
        try:
            did = int(diocese)
        except ValueError:
            return context
        allowed = accessible_diocese_ids(user)
        if allowed is None or did in allowed:
            d = Diocese.objects.filter(id=did).first()
            return {
                "level": "diocese",
                "entity": {"id": d.id, "name": d.name} if d else None,
                "scope": {"diocese_ids": [did]},
            }
    return context


class FideleDashboardApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: OpenApiTypes.OBJECT},
        tags=["dashboards"],
        summary="Tableau de bord du fidèle (vue personnelle)",
    )
    def get(self, request):
        return Response(fidele_dashboard(user=request.user))


class MyParishDashboardApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: OpenApiTypes.OBJECT},
        tags=["dashboards"],
        summary="Tableau de bord de ma paroisse (curé connecté)",
    )
    def get(self, request):
        parish_id = user_principal_parish_id(user=request.user)
        if not parish_id:
            return Response(
                {"detail": "Aucune paroisse rattachée à votre compte."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(cure_dashboard(parish_id=parish_id))


class ParishDashboardApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: OpenApiTypes.OBJECT},
        tags=["dashboards"],
        summary="Tableau de bord d'une paroisse (total fidèles, flux de dons, files)",
    )
    def get(self, request, parish_id: int):
        if not user_can_admin_parish(request.user, parish_id):
            return Response(
                {"detail": "Accès réservé à l'administrateur de la paroisse."},
                status=status.HTTP_403_FORBIDDEN,
            )
        data = cure_dashboard(parish_id=parish_id)
        if data is None:
            return Response({"detail": "Paroisse introuvable."}, status=status.HTTP_404_NOT_FOUND)
        return Response(data)


class MyDioceseDashboardApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: OpenApiTypes.OBJECT},
        tags=["dashboards"],
        summary="Tableau de bord de mon diocèse (évêque connecté)",
    )
    def get(self, request):
        diocese_id = user_principal_diocese_id(user=request.user)
        if not diocese_id:
            return Response(
                {"detail": "Aucun diocèse rattaché à votre compte."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(diocese_dashboard(diocese_id=diocese_id))


class DioceseDashboardApi(ApiAuthMixin, APIView):
    @extend_schema(
        responses={200: OpenApiTypes.OBJECT},
        tags=["dashboards"],
        summary="Tableau de bord diocésain (évêque)",
    )
    def get(self, request, diocese_id: int):
        if not user_can_admin_diocese(request.user, diocese_id):
            return Response(
                {"detail": "Accès réservé à l'administrateur du diocèse."},
                status=status.HTTP_403_FORBIDDEN,
            )
        data = diocese_dashboard(diocese_id=diocese_id)
        if data is None:
            return Response({"detail": "Diocèse introuvable."}, status=status.HTTP_404_NOT_FOUND)
        return Response(data)


class AnalyticsApi(ApiAuthMixin, APIView):
    """Analytique adaptative au rôle (curé→paroisse, évêque→diocèse, archevêque→
    province). Flux de dons + fidèles, filtres spatio-temporels, bornée au périmètre."""

    @extend_schema(
        parameters=[
            OpenApiParameter("period", OpenApiTypes.STR, description="today|week|month|quarter|year (défaut year)"),
            OpenApiParameter("from", OpenApiTypes.DATETIME, description="Début (ISO) — prioritaire sur period"),
            OpenApiParameter("to", OpenApiTypes.DATETIME, description="Fin (ISO)"),
            OpenApiParameter("granularity", OpenApiTypes.STR, description="day|week|month (défaut month)"),
            OpenApiParameter("type", OpenApiTypes.STR, description="Type de don (church_tithe, sunday_collection, …)"),
            OpenApiParameter("status", OpenApiTypes.STR, description="Statut don (défaut confirmed)"),
            OpenApiParameter("provider", OpenApiTypes.STR, description="wave|orange_money|free_money|cash"),
            OpenApiParameter("diocese", OpenApiTypes.INT, description="Drill-down : diocèse (dans le périmètre)"),
            OpenApiParameter("parish", OpenApiTypes.INT, description="Drill-down : paroisse (dans le périmètre)"),
        ],
        responses={200: OpenApiTypes.OBJECT},
        tags=["dashboards"],
        summary="Analytique scopée (dons + fidèles) — curé / évêque / archevêque",
    )
    def get(self, request):
        context = resolve_analytics_context(request.user)
        if context is None:
            return Response(
                {"detail": "Analytique réservée au clergé/administrateur scopé."},
                status=status.HTTP_403_FORBIDDEN,
            )
        context = _maybe_narrow(context, request)
        since, until, granularity = _parse_period(request)
        data = donation_analytics(
            context=context,
            since=since,
            until=until,
            granularity=granularity,
            donation_type=request.query_params.get("type") or None,
            status=request.query_params.get("status") or "confirmed",
            provider=request.query_params.get("provider") or None,
        )
        return Response(data)

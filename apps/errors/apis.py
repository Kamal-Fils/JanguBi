import structlog
from drf_spectacular.openapi import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.exception_handlers import (
    drf_default_with_modifications_exception_handler,
    hacksoft_proposed_exception_handler,
)
from apps.api.mixins import ApiAuthMixin
from apps.errors.services import trigger_errors
from apps.users.permissions import IsSuperAdmin

logger = structlog.get_logger(__name__)


class TriggerErrorApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    @extend_schema(
        responses={
            200: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description=(
                    "Objet libre : une clé par fonction `trigger_*` de `apps.errors.services`, "
                    "dont la valeur est la réponse sérialisée par chaque exception handler."
                ),
            )
        },
        tags=["errors"],
        summary="Déclencher les erreurs de démonstration (super admin)",
    )
    def get(self, request):
        data = {
            "drf_default_with_modifications": trigger_errors(drf_default_with_modifications_exception_handler),
            "hacksoft_proposed": trigger_errors(hacksoft_proposed_exception_handler),
        }

        return Response(data)


class TriggerUnhandledExceptionApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    @extend_schema(
        responses={
            500: OpenApiResponse(
                description="Lève systématiquement une exception non gérée (test du reporting d'erreurs)."
            )
        },
        tags=["errors"],
        summary="Déclencher une exception non gérée (super admin)",
    )
    def get(self, request):
        log = logger.bind()

        try:
            raise Exception("Oops")
        except Exception:
            log.exception("unhandled_exception")
            raise

        return Response()

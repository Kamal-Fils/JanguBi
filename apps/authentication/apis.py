"""
APIs d'authentification — JWT (djangorestframework-simplejwt).

Endpoints :
  POST /api/auth/jwt/login/       Connexion → access + refresh tokens
  POST /api/auth/jwt/refresh/     Renouvellement du access token
  POST /api/auth/jwt/logout/      Déconnexion (blacklist refresh token)
  POST /api/auth/jwt/logout-all/  Déconnexion de tous les appareils
  GET  /api/auth/me/              Profil de l'utilisateur connecté
  PATCH /api/auth/me/             Mise à jour du profil
"""

from django.contrib.auth import authenticate, login, logout
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.api.mixins import ApiAuthMixin
from apps.api.serializers import ErrorResponseSerializer
from apps.authentication.serializers import CustomTokenObtainPairSerializer
from apps.authentication.services import auth_logout, auth_logout_all_devices
from apps.core.throttling import LoginRateThrottle
from apps.users.selectors import user_get_login_data
from apps.users.serializers import MeOutputSerializer


class UserJwtLoginInputSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class UserJwtLoginUserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.EmailField()
    role = serializers.CharField()
    pastoral_role = serializers.CharField(allow_null=True)
    onboarding_state = serializers.CharField()
    is_admin = serializers.BooleanField()


class UserJwtLoginOutputSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = UserJwtLoginUserSerializer()


class UserJwtRefreshInputSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class UserJwtRefreshOutputSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField(required=False)


class UserJwtLogoutInputSerializer(serializers.Serializer):
    refresh = serializers.CharField(help_text="Refresh token à blacklister.")


class UserSessionLoginOutputSerializer(serializers.Serializer):
    session = serializers.CharField()
    data = MeOutputSerializer()  # type: ignore[assignment]  # drf-stubs : serializer imbriqué nommé `data` masque Serializer.data

# ---------------------------------------------------------------------------
# JWT Login
# ---------------------------------------------------------------------------

@extend_schema(
    tags=["Authentification"],
    summary="Connexion JWT",
    description=(
        "Authentifie l'utilisateur et retourne un access token (60 min) "
        "et un refresh token (7 jours). "
        "Le compte doit être actif ET l'email vérifié."
    ),
    request=UserJwtLoginInputSerializer,
    responses={
        200: UserJwtLoginOutputSerializer,
        400: ErrorResponseSerializer,
        401: ErrorResponseSerializer,
    },
)
class UserJwtLoginApi(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = [LoginRateThrottle]


# ---------------------------------------------------------------------------
# JWT Refresh
# ---------------------------------------------------------------------------

@extend_schema(
    tags=["Authentification"],
    summary="Renouvellement du access token",
    description="Échange un refresh token valide contre un nouveau access token.",
    request=UserJwtRefreshInputSerializer,
    responses={
        200: UserJwtRefreshOutputSerializer,
        401: ErrorResponseSerializer,
    },
)
class UserJwtRefreshApi(TokenRefreshView):
    pass


# ---------------------------------------------------------------------------
# JWT Logout (appareil courant)
# ---------------------------------------------------------------------------

@extend_schema(
    tags=["Authentification"],
    summary="Déconnexion (appareil courant)",
    description=(
        "Blackliste le refresh token fourni. "
        "L'access token reste valide jusqu'à son expiration naturelle (60 min max). "
        "Pour révoquer tous les appareils, utiliser /logout-all/."
    ),
    request=UserJwtLogoutInputSerializer,
    responses={
        204: OpenApiResponse(description="Déconnexion réussie"),
        400: ErrorResponseSerializer,
    },
)
class UserJwtLogoutApi(ApiAuthMixin, APIView):
    def post(self, request):
        serializer = UserJwtLogoutInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            token = RefreshToken(serializer.validated_data["refresh"])
            token.blacklist()
        except TokenError:
            return Response(
                {"detail": "Token invalide ou déjà révoqué."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        auth_logout(request.user, ip=_get_client_ip(request))
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# JWT Logout All Devices
# ---------------------------------------------------------------------------

@extend_schema(
    tags=["Authentification"],
    summary="Déconnexion de tous les appareils",
    description=(
        "Invalide TOUS les JWT actifs de l'utilisateur via rotation du jwt_key. "
        "Utile en cas de suspicion de compromission."
    ),
    responses={204: OpenApiResponse(description="Tous les appareils déconnectés")},
)
class UserJwtLogoutAllApi(ApiAuthMixin, APIView):
    def post(self, request):
        auth_logout_all_devices(request.user, ip=_get_client_ip(request))
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Session Login / Logout (Django Admin + fallback)
# ---------------------------------------------------------------------------

class UserSessionLoginInputSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()


@extend_schema(
    tags=["Authentification"],
    summary="Connexion Session-based",
    description="Authentifie via les mécanismes de session Django. Utilisé pour l'admin ou cas spécifiques.",
    request=UserSessionLoginInputSerializer,
    responses={
        200: UserSessionLoginOutputSerializer,
        400: ErrorResponseSerializer,
    },
)
class UserSessionLoginApi(APIView):
    def post(self, request):
        serializer = UserSessionLoginInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(request, **serializer.validated_data)
        if user is None:
            return Response(
                {"detail": "Identifiants invalides."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        login(request, user)
        data = user_get_login_data(user=user)
        return Response({"session": request.session.session_key, "data": data})


@extend_schema(
    tags=["Authentification"],
    summary="Déconnexion Session-based",
    responses={204: None},
)
class UserSessionLogoutApi(APIView):
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# /me/ — Profil de l'utilisateur connecté
# ---------------------------------------------------------------------------

@extend_schema(
    tags=["Authentification"],
    summary="Profil utilisateur connecté",
    description="Retourne les données complètes de l'utilisateur authentifié (ID, email, rôle, etc.).",
    responses={200: MeOutputSerializer},
)
class UserMeApi(ApiAuthMixin, APIView):
    def get(self, request):
        data = user_get_login_data(user=request.user)
        return Response(data)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_client_ip(request) -> str | None:
    """
    Récupère l'IP réelle depuis X-Forwarded-For si configuré,
    sinon REMOTE_ADDR. Ne fait confiance à X-Forwarded-For que si
    le proxy inverse est configuré pour le nettoyer (section 5.2).
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")

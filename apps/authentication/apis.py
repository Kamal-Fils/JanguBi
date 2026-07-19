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
from drf_spectacular.openapi import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.api.mixins import ApiAuthMixin
from apps.api.serializers import ErrorResponseSerializer
from apps.authentication.cookies import (
    AUTH_TRANSPORT_COOKIE,
    AUTH_TRANSPORT_HEADER,
    delete_refresh_cookie,
    read_refresh_token,
    set_refresh_cookie,
    wants_cookie_transport,
)
from apps.authentication.serializers import CustomTokenObtainPairSerializer
from apps.authentication.services import auth_logout, auth_logout_all_devices
from apps.core.throttling import LoginRateThrottle
from apps.users.selectors import user_get_login_data
from apps.users.serializers import MeOutputSerializer

# En-tête documenté sur les endpoints JWT : il permet au client web de réclamer
# le transport du refresh token par cookie HttpOnly. Cf. apps/authentication/cookies.py.
AUTH_TRANSPORT_PARAMETER = OpenApiParameter(
    name=AUTH_TRANSPORT_HEADER,
    type=OpenApiTypes.STR,
    location=OpenApiParameter.HEADER,
    required=False,
    enum=[AUTH_TRANSPORT_COOKIE],
    description=(
        "Transport souhaité pour le refresh token. Avec la valeur `cookie` "
        "(clients navigateur), le jeton est posé dans un cookie HttpOnly et "
        "**omis du corps de réponse**. Sans cet en-tête (clients natifs / mobile), "
        "le jeton est renvoyé dans le corps comme auparavant."
    ),
)


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
    # Omis en mode cookie (en-tête `X-Auth-Transport: cookie`) : le jeton est
    # alors posé dans un cookie HttpOnly et n'apparaît nulle part dans le corps.
    refresh = serializers.CharField(
        required=False,
        help_text="Absent quand le transport par cookie est demandé.",
    )
    user = UserJwtLoginUserSerializer()


class UserJwtRefreshInputSerializer(serializers.Serializer):
    # Facultatif : en mode cookie, le jeton est lu dans le cookie HttpOnly.
    refresh = serializers.CharField(
        required=False,
        help_text="Inutile si le refresh token est porté par le cookie HttpOnly.",
    )


class UserJwtRefreshOutputSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField(
        required=False,
        help_text="Absent quand le transport par cookie est demandé.",
    )


class UserJwtLogoutInputSerializer(serializers.Serializer):
    refresh = serializers.CharField(
        required=False,
        help_text="Refresh token à blacklister. Inutile si porté par le cookie HttpOnly.",
    )


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
        "Authentifie l'utilisateur et retourne un access token (30 min par défaut, "
        "réglable via JWT_ACCESS_TOKEN_LIFETIME_MINUTES) et un refresh token (7 jours). "
        "Le compte doit être actif ET l'email vérifié.\n\n"
        "Avec l'en-tête `X-Auth-Transport: cookie`, le refresh token est posé dans un "
        "cookie HttpOnly et **omis du corps de réponse** — il devient alors illisible "
        "depuis JavaScript."
    ),
    parameters=[AUTH_TRANSPORT_PARAMETER],
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

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if response.status_code != status.HTTP_200_OK:
            return response
        if not wants_cookie_transport(request):
            # Client natif / mobile : comportement historique, jeton dans le corps.
            return response

        # Mode cookie : le jeton doit VRAIMENT disparaître du corps. Le laisser
        # « aussi » dans la réponse annulerait le bénéfice — une XSS pourrait le
        # lire au moment de la connexion, qui est précisément le moment où il est
        # émis pour 7 jours.
        refresh = response.data.pop("refresh", None)
        if refresh:
            set_refresh_cookie(response, refresh)
        return response


# ---------------------------------------------------------------------------
# JWT Refresh
# ---------------------------------------------------------------------------

@extend_schema(
    tags=["Authentification"],
    summary="Renouvellement du access token",
    description=(
        "Échange un refresh token valide contre un nouveau access token.\n\n"
        "Le jeton est lu **en priorité dans le cookie HttpOnly**, avec repli sur le "
        "champ `refresh` du corps (clients natifs / mobile). La rotation étant active "
        "(`ROTATE_REFRESH_TOKENS`), le nouveau jeton remplace le cookie."
    ),
    parameters=[AUTH_TRANSPORT_PARAMETER],
    request=UserJwtRefreshInputSerializer,
    responses={
        200: UserJwtRefreshOutputSerializer,
        401: ErrorResponseSerializer,
    },
)
class UserJwtRefreshApi(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        refresh, from_cookie = read_refresh_token(request)

        if not refresh:
            # Ni cookie ni corps : échec explicite, plutôt qu'un 500 sur un
            # sérialiseur dont le champ est devenu facultatif.
            return Response(
                {"detail": "Refresh token absent (ni cookie, ni corps de requête)."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        serializer = self.get_serializer(data={"refresh": refresh})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken(exc.args[0]) from exc

        data = dict(serializer.validated_data)
        response = Response(data, status=status.HTTP_200_OK)

        # On reste en mode cookie si le client le demande OU si le jeton venait
        # du cookie : sinon la rotation laisserait dans le navigateur un cookie
        # périmé et déjà blacklisté, et la session mourrait au refresh suivant.
        if wants_cookie_transport(request) or from_cookie:
            rotated = data.pop("refresh", None)
            response.data = data
            if rotated:
                set_refresh_cookie(response, rotated)

        return response


# ---------------------------------------------------------------------------
# JWT Logout (appareil courant)
# ---------------------------------------------------------------------------

@extend_schema(
    tags=["Authentification"],
    summary="Déconnexion (appareil courant)",
    description=(
        "Blackliste le refresh token, lu **en priorité dans le cookie HttpOnly** avec "
        "repli sur le corps de requête, puis efface le cookie. "
        "L'access token reste valide jusqu'à son expiration naturelle (30 min max par défaut). "
        "Pour révoquer tous les appareils, utiliser /logout-all/."
    ),
    parameters=[AUTH_TRANSPORT_PARAMETER],
    request=UserJwtLogoutInputSerializer,
    responses={
        204: OpenApiResponse(description="Déconnexion réussie"),
        400: ErrorResponseSerializer,
    },
)
class UserJwtLogoutApi(ApiAuthMixin, APIView):
    def post(self, request):
        refresh, _ = read_refresh_token(request)

        if not refresh:
            return Response(
                {"detail": "Refresh token absent (ni cookie, ni corps de requête)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(refresh)
            token.blacklist()
        except TokenError:
            # Le jeton est déjà mort : la session l'est aussi. On efface tout de
            # même le cookie — le laisser en place condamnerait le navigateur à
            # renvoyer indéfiniment un jeton révoqué.
            response = Response(
                {"detail": "Token invalide ou déjà révoqué."},
                status=status.HTTP_400_BAD_REQUEST,
            )
            return delete_refresh_cookie(response)

        auth_logout(request.user, ip=_get_client_ip(request))
        return delete_refresh_cookie(Response(status=status.HTTP_204_NO_CONTENT))


# ---------------------------------------------------------------------------
# JWT Logout All Devices
# ---------------------------------------------------------------------------

@extend_schema(
    tags=["Authentification"],
    summary="Déconnexion de tous les appareils",
    description=(
        "Invalide TOUS les JWT actifs de l'utilisateur via rotation du jwt_key, "
        "et efface le cookie de refresh de l'appareil courant. "
        "Utile en cas de suspicion de compromission."
    ),
    parameters=[AUTH_TRANSPORT_PARAMETER],
    request=None,
    responses={204: OpenApiResponse(description="Tous les appareils déconnectés")},
)
class UserJwtLogoutAllApi(ApiAuthMixin, APIView):
    def post(self, request):
        auth_logout_all_devices(request.user, ip=_get_client_ip(request))
        # La rotation du jwt_key tue les jetons côté serveur ; le cookie doit
        # disparaître côté navigateur, sinon il subsiste 7 jours pour rien.
        return delete_refresh_cookie(Response(status=status.HTTP_204_NO_CONTENT))


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

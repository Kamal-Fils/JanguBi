from django.urls import path

from .apis import (
    UserJwtLoginApi,
    UserJwtLogoutAllApi,
    UserJwtLogoutApi,
    UserJwtRefreshApi,
    UserMeApi,
)

urlpatterns = [
    # --- JWT (principal — SPA headless) ---
    path("jwt/login/", UserJwtLoginApi.as_view(), name="jwt-login"),
    path("jwt/refresh/", UserJwtRefreshApi.as_view(), name="jwt-refresh"),
    path("jwt/logout/", UserJwtLogoutApi.as_view(), name="jwt-logout"),
    path("jwt/logout-all/", UserJwtLogoutAllApi.as_view(), name="jwt-logout-all"),

    # --- Session (Django Admin + fallback Safari) ---
    # path("session/login/", UserSessionLoginApi.as_view(), name="session-login"),
    # path("session/logout/", UserSessionLogoutApi.as_view(), name="session-logout"),

    # --- Profil connecté ---
    path("me/", UserMeApi.as_view(), name="me"),
]

from django.urls import path

from .apis import (
    EmailChangeConfirmApi,
    EmailChangeRequestApi,
    EmailChangeRevertApi,
    EmailVerifyApi,
    FideleRegisterApi,
    PasswordChangeApi,
    PasswordResetConfirmApi,
    PasswordResetRequestApi,
    UserAdminCreateApi,
    UserAuditLogApi,
    UserDetailApi,
    UserHardDeleteApi,
    UserListApi,
    UserMeDeleteApi,
    UserMeDetailApi,
    UserMeUpdateApi,
    UserSoftDeleteApi,
    UserToggleActiveApi,
)

urlpatterns = [
    # -------------------------------------------------------------------------
    # Inscription
    # -------------------------------------------------------------------------
    path("register/", FideleRegisterApi.as_view(), name="register"),
    path("verify-email/", EmailVerifyApi.as_view(), name="verify-email"),

    # -------------------------------------------------------------------------
    # Mot de passe
    # -------------------------------------------------------------------------
    path("password/reset/request/", PasswordResetRequestApi.as_view(), name="password-reset-request"),
    path("password/reset/confirm/", PasswordResetConfirmApi.as_view(), name="password-reset-confirm"),
    path("password/change/", PasswordChangeApi.as_view(), name="password-change"),

    # -------------------------------------------------------------------------
    # Email
    # -------------------------------------------------------------------------
    path("email/change/request/", EmailChangeRequestApi.as_view(), name="email-change-request"),
    path("email/change/confirm/", EmailChangeConfirmApi.as_view(), name="email-change-confirm"),
    path("email/change/revert/", EmailChangeRevertApi.as_view(), name="email-change-revert"),

    # -------------------------------------------------------------------------
    # Profil (propriétaire)
    # -------------------------------------------------------------------------
    path("me/", UserMeDetailApi.as_view(), name="me-detail"),
    path("me/update/", UserMeUpdateApi.as_view(), name="me-update"),
    path("me/delete/", UserMeDeleteApi.as_view(), name="me-delete"),

    # -------------------------------------------------------------------------
    # Administration
    # -------------------------------------------------------------------------
    path("", UserListApi.as_view(), name="list"),
    path("admin/create/", UserAdminCreateApi.as_view(), name="admin-create"),
    path("<uuid:user_id>/", UserDetailApi.as_view(), name="detail"),
    path("<uuid:user_id>/toggle-active/", UserToggleActiveApi.as_view(), name="toggle-active"),
    path("<uuid:user_id>/delete/", UserSoftDeleteApi.as_view(), name="soft-delete"),
    path("<uuid:user_id>/hard-delete/", UserHardDeleteApi.as_view(), name="hard-delete"),
    path("<uuid:user_id>/audit-logs/", UserAuditLogApi.as_view(), name="audit-logs"),
]

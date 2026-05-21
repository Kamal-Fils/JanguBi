import uuid

from django.contrib.auth.models import AbstractBaseUser, Group, Permission, PermissionsMixin
from django.contrib.auth.models import BaseUserManager as DjangoBaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _
from phonenumber_field.modelfields import PhoneNumberField

from apps.common.models import BaseModel
from apps.users.enums import AuditEvent, PastoralRole, Title, UserOnboardingState, UserRole


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class BaseUserManager(DjangoBaseUserManager):
    def create_user(
        self,
        email: str,
        role: str,
        phone_number: str,
        password: str | None = None,
        is_verified: bool = False,
        is_active: bool = False,
        is_staff: bool = False,
        is_admin: bool = False,
        **extra_fields,
    ) -> "BaseUser":
        if not email:
            raise ValueError("L'adresse email est obligatoire.")
        if not role:
            raise ValueError("Le rôle est obligatoire.")

        normalized_email = self.normalize_email(email).lower()

        user = self.model(
            email=normalized_email,
            phone_number=phone_number,
            role=role,
            is_staff=is_staff,
            is_active=is_active,
            is_admin=is_admin,
            is_verified=is_verified,
            **extra_fields,
        )

        if password is not None:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.full_clean()
        user.save(using=self._db)
        return user

    def create_superuser(
        self,
        email: str,
        password: str,
        phone_number: str = "+221771000000",
        **extra_fields,
    ) -> "BaseUser":
        return self.create_user(
            email=email,
            password=password,
            phone_number=phone_number,
            role=UserRole.SUPER_ADMIN,
            is_superuser=True,
            is_staff=True,
            is_admin=True,
            is_verified=True,
            is_active=True,
            **extra_fields,
        )


# ---------------------------------------------------------------------------
# Modèle utilisateur principal
# ---------------------------------------------------------------------------

class BaseUser(BaseModel, AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(
        verbose_name=_("adresse email"),
        max_length=255,
        unique=True,
        db_index=True,
    )
    phone_number = PhoneNumberField(
        _("numéro de téléphone"),
        unique=True,
        db_index=True,
    )
    role = models.CharField(
        _("rôle"),
        max_length=20,
        choices=UserRole.choices,
        db_index=True,
    )
    is_verified = models.BooleanField(
        _("email vérifié"),
        default=False,
        help_text=_("L'utilisateur a validé son adresse email."),
    )
    is_active = models.BooleanField(
        _("actif"),
        default=False,
        help_text=_("Désactivez plutôt que de supprimer le compte."),
    )
    is_staff = models.BooleanField(
        _("membre du staff"),
        default=False,
        help_text=_("Accès à l'interface d'administration Django."),
    )
    is_admin = models.BooleanField(
        _("administrateur"),
        default=False,
    )

    # UUID rotatif : invalide TOUS les JWT actifs de l'utilisateur en une mise à jour
    jwt_key = models.UUIDField(
        default=uuid.uuid4,
        help_text=_("Rotation invalide tous les tokens JWT actifs."),
    )

    # Dimension pastorale (clergé/fidèle — orthogonale au rôle admin)
    pastoral_role = models.CharField(
        _("rôle pastoral"),
        max_length=20,
        choices=PastoralRole.choices,
        null=True,
        blank=True,
        db_index=True,
    )

    # Onboarding — état du parcours d'inscription
    onboarding_state = models.CharField(
        _("état onboarding"),
        max_length=30,
        choices=UserOnboardingState.choices,
        default=UserOnboardingState.PENDING_EMAIL_VERIFICATION,
        db_index=True,
    )

    # Hiérarchie territoriale (auto-remplie par signal depuis Profile.primary_parish)
    diocese = models.ForeignKey(
        "org.Diocese",
        verbose_name=_("diocèse"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
    )
    province = models.ForeignKey(
        "org.Province",
        verbose_name=_("province"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
    )
    religious_community = models.ForeignKey(
        "org.ReligiousCommunity",
        verbose_name=_("communauté religieuse"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
    )
    followed_parishes = models.ManyToManyField(
        "org.Parish",
        verbose_name=_("paroisses suivies"),
        blank=True,
        related_name="followers",
    )

    groups = models.ManyToManyField(
        Group,
        verbose_name=_("groupes"),
        blank=True,
        related_name="baseuser_set",
    )
    user_permissions = models.ManyToManyField(
        Permission,
        verbose_name=_("permissions"),
        blank=True,
        related_name="baseuser_permissions_set",
    )

    objects = BaseUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["phone_number"]

    class Meta:
        verbose_name = _("utilisateur")
        verbose_name_plural = _("utilisateurs")

    def __str__(self) -> str:
        return self.email

    def rotate_jwt_key(self) -> None:
        """Invalide tous les JWT actifs. Appelé après password change / email change revert."""
        self.jwt_key = uuid.uuid4()
        self.save(update_fields=["jwt_key", "updated_at"])

    def get_scope_ids(self) -> dict:
        """Retourne les IDs territoriaux pour le scoping du contenu."""
        parish_ids = list(self.followed_parishes.values_list("id", flat=True))
        try:
            if self.profile.primary_parish_id:
                parish_ids.append(self.profile.primary_parish_id)
        except Profile.DoesNotExist:
            pass
        return {
            "parish_ids": parish_ids,
            "diocese_id": self.diocese_id,
            "province_id": self.province_id,
        }


# ---------------------------------------------------------------------------
# Profil utilisateur
# ---------------------------------------------------------------------------

class Profile(BaseModel):
    user = models.OneToOneField(
        BaseUser,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    first_name = models.CharField(_("prénom"), max_length=50, blank=True, default="")
    last_name = models.CharField(_("nom"), max_length=50, blank=True, default="")
    title = models.CharField(
        _("civilité"),
        max_length=10,
        choices=Title.choices,
        blank=True,
        default="",
    )
    date_of_birth = models.DateField(_("date de naissance"), null=True, blank=True)
    phone = PhoneNumberField(_("téléphone"), blank=True, null=True)
    avatar = models.ImageField(_("avatar"), upload_to="avatars/", blank=True, null=True)

    primary_parish = models.ForeignKey(
        "org.Parish",
        verbose_name=_("paroisse principale"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="primary_members",
    )

    class Meta:
        verbose_name = _("profil")
        verbose_name_plural = _("profils")

    def __str__(self) -> str:
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name or str(self.user.email)


# ---------------------------------------------------------------------------
# Journal d'audit sécurité (SQL immuable — jamais supprimé)
# ---------------------------------------------------------------------------

class SecurityAuditLog(BaseModel):
    """
    Trace immuable de tous les événements de sécurité.
    Stockage SQL (Cold Data) — complémentaire au Hot Data Redis des OTP.
    Conforme OWASP ASVS V7.
    """

    user = models.ForeignKey(
        BaseUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        help_text=_("NULL si l'utilisateur a été supprimé définitivement."),
    )
    event = models.CharField(
        _("événement"),
        max_length=50,
        choices=AuditEvent.choices,
        db_index=True,
    )
    ip_address = models.GenericIPAddressField(
        _("adresse IP"),
        null=True,
        blank=True,
        help_text=_("IPv4 ou IPv6 nettoyée par le reverse proxy."),
    )
    user_agent = models.TextField(_("user agent"), blank=True, default="")
    metadata = models.JSONField(
        _("métadonnées"),
        default=dict,
        blank=True,
        help_text=_("Données contextuelles non sensibles (ex: nouvelle email masquée)."),
    )

    class Meta:
        verbose_name = _("journal de sécurité")
        verbose_name_plural = _("journaux de sécurité")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "event"]),
            models.Index(fields=["event", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"[{self.event}] {self.user} — {self.created_at:%Y-%m-%d %H:%M}"

from django.db import models
from django.utils.translation import gettext_lazy as _


class PastoralRole(models.TextChoices):
    FIDELE     = ("fidele",     _("Fidèle"))
    RELIGIEUX  = ("religieux",  _("Religieux/Religieuse"))
    DIACRE     = ("diacre",     _("Diacre"))
    PRETRE     = ("pretre",     _("Prêtre"))
    EVEQUE     = ("eveque",     _("Évêque"))
    ARCHEVEQUE = ("archeveque", _("Archevêque"))


class UserOnboardingState(models.TextChoices):
    PENDING_EMAIL_VERIFICATION = ("pending_email",  _("Email à vérifier"))
    PENDING_PARISH_SELECTION   = ("pending_parish", _("Paroisse à sélectionner"))
    COMPLETED                  = ("completed",      _("Complété"))


class UserRole(models.TextChoices):
    SUPER_ADMIN    = ("super_admin",    _("Super Admin"))
    PROVINCE_ADMIN = ("province_admin", _("Admin Province"))
    DIOCESE_ADMIN  = ("diocese_admin",  _("Admin Diocèse"))
    PARISH_ADMIN   = ("parish_admin",   _("Admin Paroisse"))
    CHURCH_ADMIN   = ("church_admin",   _("Admin Église"))
    FIDELE         = ("fidele",         _("Fidèle"))


class RoleScope(models.TextChoices):
    """
    Niveau territorial d'une capacité administrative (RoleAssignment).

    Permet de cloisonner les permissions : un PARISH_ADMIN scopé à la paroisse A
    (= le curé) ne peut pas agir sur la paroisse B. Un CHURCH_ADMIN scopé à une
    église (= un vicaire / responsable d'église) n'agit que sur cette église.
    """

    GLOBAL   = ("global",   _("Global"))
    PROVINCE = ("province", _("Province"))
    DIOCESE  = ("diocese",  _("Diocèse"))
    PARISH   = ("parish",   _("Paroisse"))
    CHURCH   = ("church",   _("Église"))


class Title(models.TextChoices):
    MR  = ("MR",  _("M."))
    MRS = ("MRS", _("Mme"))


class AuditEvent(models.TextChoices):
    """Événements tracés dans SecurityAuditLog."""

    REGISTER                = ("REGISTER",               _("Inscription"))
    EMAIL_VERIFIED          = ("EMAIL_VERIFIED",          _("Email vérifié"))
    LOGIN                   = ("LOGIN",                   _("Connexion"))
    LOGOUT                  = ("LOGOUT",                  _("Déconnexion"))
    PASSWORD_RESET_REQUEST  = ("PWD_RESET_REQUEST",       _("Demande réinitialisation MDP"))
    PASSWORD_RESET_CONFIRM  = ("PWD_RESET_CONFIRM",       _("Réinitialisation MDP confirmée"))
    PASSWORD_CHANGED        = ("PWD_CHANGED",             _("Mot de passe modifié"))
    EMAIL_CHANGE_REQUEST    = ("EMAIL_CHANGE_REQUEST",    _("Demande changement email"))
    EMAIL_CHANGE_CONFIRM    = ("EMAIL_CHANGE_CONFIRM",    _("Changement email confirmé"))
    EMAIL_CHANGE_REVERTED   = ("EMAIL_CHANGE_REVERTED",   _("Changement email annulé"))
    ACCOUNT_ACTIVATED       = ("ACCOUNT_ACTIVATED",       _("Compte activé"))
    ACCOUNT_DEACTIVATED     = ("ACCOUNT_DEACTIVATED",     _("Compte désactivé"))
    ACCOUNT_SOFT_DELETED    = ("ACCOUNT_SOFT_DELETED",    _("Compte supprimé (soft)"))
    ACCOUNT_HARD_DELETED    = ("ACCOUNT_HARD_DELETED",    _("Compte supprimé (définitif)"))
    ADMIN_CREATED_ACCOUNT   = ("ADMIN_CREATED",           _("Compte créé par admin"))
    PROFILE_UPDATED         = ("PROFILE_UPDATED",         _("Profil mis à jour"))

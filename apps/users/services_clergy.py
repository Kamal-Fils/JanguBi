"""Services d'écriture pour la chaîne de validation des comptes clergé.

Deux voies mènent à un compte clergé (SRS — chaîne de validation) :

- **Invitation** (``apps.clergy_accounts``) : l'autorité supérieure émet un token ;
  l'accepter VAUT validation → le compte naît ``APPROVED``.
- **Auto-déclaration** : l'utilisateur revendique un rôle pastoral ; son compte
  reste ``PENDING`` jusqu'à l'approbation ou le refus de son supérieur
  territorial. Ce module implémente cette seconde branche.

Le cloisonnement territorial est **fail-closed** : il délègue à
``user_is_in_scope_of`` (source de vérité RoleAssignment), comme le reste du
module users. Un validateur sans affectation territoriale ne peut trancher
AUCUN dossier hors du sien.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import ApplicationError
from apps.users.enums import (
    CLERGY_PASTORAL_ROLES,
    AuditEvent,
    ClergyValidationStatus,
    PastoralRole,
    UserRole,
)
from apps.users.models import BaseUser, ClergySelfDeclaration

# Rôles pastoraux qu'un évêque / archevêque peut valider lui-même. Aligné sur
# ``_EVEQUE_INVITABLE_ROLES`` (apps.clergy_accounts.services) : l'autorité de
# validation doit refléter exactement l'autorité d'invitation.
_BISHOP_VALIDATABLE_ROLES = frozenset({
    PastoralRole.PRETRE,
    PastoralRole.DIACRE,
    PastoralRole.RELIGIEUX,
})

# Nommer un évêque ou un archevêque relève du seul super_admin.
_SUPER_ADMIN_ONLY_ROLES = frozenset({PastoralRole.EVEQUE, PastoralRole.ARCHEVEQUE})

_BISHOP_PASTORAL_ROLES = frozenset({PastoralRole.EVEQUE, PastoralRole.ARCHEVEQUE})

_MAX_REJECTION_REASON_LEN = 500

_MAX_DECLARATION_MESSAGE_LEN = 2000


def user_can_validate_clergy(*, validator: BaseUser, pastoral_role: str) -> bool:
    """Qui peut trancher quel rôle pastoral (même règle que ``_can_invite``)."""
    if validator.role == UserRole.SUPER_ADMIN:
        return True
    if pastoral_role in _SUPER_ADMIN_ONLY_ROLES:
        return False
    return (
        validator.pastoral_role in _BISHOP_PASTORAL_ROLES
        and pastoral_role in _BISHOP_VALIDATABLE_ROLES
    )


def _assert_can_decide(*, user: BaseUser, performed_by: BaseUser) -> ClergySelfDeclaration:
    """Garde commune approbation / refus. Messages user-safe (aucun détail interne).

    Retourne la demande en cours : c'est ELLE qui porte le rôle revendiqué, pas
    ``user.pastoral_role`` (qui reste laïc tant que rien n'est approuvé — cf.
    ``ClergySelfDeclaration``). Verrouillée en base le temps de la décision, pour
    que deux validateurs concurrents ne tranchent pas la même demande deux fois.
    """
    declaration = (
        ClergySelfDeclaration.objects
        .select_for_update()
        .select_related("parish")
        .filter(user=user, status=ClergySelfDeclaration.Status.PENDING)
        .first()
    )

    if declaration is None:
        raise ApplicationError("Aucune demande de compte clergé en attente pour ce compte.")

    if user.clergy_validation_status != ClergyValidationStatus.PENDING:
        raise ApplicationError("Cette demande a déjà été traitée.")

    if user == performed_by:
        raise ApplicationError("Vous ne pouvez pas valider votre propre compte.")

    claimed_role = declaration.claimed_pastoral_role
    if not user_can_validate_clergy(validator=performed_by, pastoral_role=claimed_role):
        raise ApplicationError("Vous n'avez pas les droits pour valider ce type de compte clergé.")

    # Cloisonnement territorial (fail-closed) : un évêque ne tranche que dans son
    # diocèse. Sans cette garde, tout évêque validerait le clergé de la plateforme.
    # On se cale sur la paroisse REVENDIQUÉE dans la demande, pas sur la paroisse
    # du profil : un candidat dont l'onboarding n'est pas terminé n'a pas encore
    # de paroisse principale et serait sinon invisible de son propre évêque.
    if not _validator_covers_parish(performed_by, declaration.parish_id):
        raise ApplicationError("Cette demande n'appartient pas à votre périmètre.")

    return declaration


def _validator_covers_parish(validator: BaseUser, parish_id: int) -> bool:
    """Le validateur a-t-il autorité sur la paroisse revendiquée ? (fail-closed)"""
    from apps.users.scoping import accessible_parish_ids, is_global_admin

    if is_global_admin(validator):
        return True
    parish_ids = accessible_parish_ids(validator)  # set (None réservé au global, déjà traité)
    if not parish_ids:
        return False
    return parish_id in parish_ids


_ROLE_LABELS: dict[str, str] = {
    PastoralRole.PRETRE: "Prêtre",
    PastoralRole.DIACRE: "Diacre",
    PastoralRole.RELIGIEUX: "Religieux/Religieuse",
    PastoralRole.EVEQUE: "Évêque",
    PastoralRole.ARCHEVEQUE: "Archevêque",
}


def _role_label(pastoral_role: str) -> str:
    return _ROLE_LABELS.get(pastoral_role, pastoral_role)


def _notify(user: BaseUser, template_prefix: str, ctx: dict[str, Any]) -> None:
    """Notification au demandeur via le pipeline Email + Celery (jamais de SMTP direct)."""
    from apps.users.services import _send_email_safe

    _send_email_safe(template_prefix, {"user": user, **ctx}, user.email)


def _send_to(email: str, template_prefix: str, ctx: dict[str, Any]) -> None:
    """Notification à un destinataire tiers (autorité validante). Même pipeline."""
    from apps.users.services import _send_email_safe

    _send_email_safe(template_prefix, ctx, email)


@transaction.atomic
def clergy_declaration_submit(
    *,
    user: BaseUser,
    claimed_pastoral_role: str,
    parish_id: int,
    justification_file_id: int,
    message: str = "",
    ip: str | None = None,
) -> ClergySelfDeclaration:
    """Dépose une auto-déclaration de clergé : le compte entre en file d'attente.

    N'accorde AUCUNE capacité : ``user.pastoral_role`` n'est délibérément pas
    touché (cf. la docstring de ``ClergySelfDeclaration`` — l'écrire ici serait
    une escalade de privilèges en libre-service). Seul
    ``clergy_validation_status`` passe à ``PENDING``, ce qui est un état
    d'attente, jamais un droit.
    """
    from apps.files.models import File
    from apps.org.models import Parish
    from apps.users.selectors import clergy_declaration_validator_emails

    if claimed_pastoral_role not in CLERGY_PASTORAL_ROLES:
        raise ApplicationError("Ce rôle pastoral ne relève pas de la validation du clergé.")

    # Déjà clergé validé : il n'y a rien à revendiquer.
    if (
        user.pastoral_role in CLERGY_PASTORAL_ROLES
        and user.clergy_validation_status == ClergyValidationStatus.APPROVED
    ):
        raise ApplicationError("Votre compte clergé est déjà validé.")

    # Re-soumission interdite tant que rien n'est tranché ; autorisée après un refus.
    if ClergySelfDeclaration.objects.filter(
        user=user, status=ClergySelfDeclaration.Status.PENDING
    ).exists():
        raise ApplicationError(
            "Une demande est déjà en cours d'examen. Attendez la décision de votre autorité."
        )

    parish = Parish.objects.select_related("diocese").filter(pk=parish_id).first()
    if parish is None:
        raise ApplicationError("Paroisse de rattachement introuvable.")

    justification = File.objects.filter(pk=justification_file_id, uploaded_by=user).first()
    if justification is None:
        raise ApplicationError("Justificatif introuvable.")
    # Un fichier dont le téléversement n'est pas terminé n'a pas de contenu :
    # l'attacher produirait une demande sans preuve (cf. apps.documents.services).
    if not justification.is_valid:
        raise ApplicationError("Le téléversement du justificatif n'est pas terminé.")

    message = (message or "").strip()
    if len(message) > _MAX_DECLARATION_MESSAGE_LEN:
        raise ApplicationError(
            f"Le message ne peut pas dépasser {_MAX_DECLARATION_MESSAGE_LEN} caractères."
        )

    declaration = ClergySelfDeclaration.objects.create(
        user=user,
        claimed_pastoral_role=claimed_pastoral_role,
        parish=parish,
        justification_file=justification,
        message=message,
        status=ClergySelfDeclaration.Status.PENDING,
    )

    user.clergy_validation_status = ClergyValidationStatus.PENDING
    user.save(update_fields=["clergy_validation_status", "updated_at"])

    from apps.users.services import _audit

    _audit(
        user,
        AuditEvent.CLERGY_DECLARATION_SUBMITTED,
        ip,
        {"claimed_pastoral_role": claimed_pastoral_role, "parish_id": parish.id},
    )

    # Accusé de réception au demandeur.
    _notify(
        user,
        "clergy_declaration_received",
        {"claimed_role_label": _role_label(claimed_pastoral_role), "parish_name": parish.name},
    )

    # Alerte aux autorités compétentes : sans elle, la file se remplit sans que
    # personne ne sache qu'elle existe.
    for validator_email in clergy_declaration_validator_emails(diocese_id=parish.diocese_id):
        _send_to(
            validator_email,
            "clergy_declaration_submitted",
            {
                "candidate_email": user.email,
                "claimed_role_label": _role_label(claimed_pastoral_role),
                "parish_name": parish.name,
            },
        )

    return declaration


@transaction.atomic
def user_validate_clergy_account(
    *,
    user: BaseUser,
    performed_by: BaseUser,
    ip: str | None = None,
) -> BaseUser:
    """Approuve une auto-déclaration : c'est ICI que le rôle pastoral est accordé."""
    declaration = _assert_can_decide(user=user, performed_by=performed_by)

    declaration.status = ClergySelfDeclaration.Status.APPROVED
    declaration.reviewed_by = performed_by
    declaration.reviewed_at = timezone.now()
    declaration.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])

    # Le rôle revendiqué ne devient réel qu'à cet instant précis — après revue
    # humaine. C'est la contrepartie de ne pas l'avoir écrit à la déclaration.
    user.pastoral_role = declaration.claimed_pastoral_role
    user.clergy_validation_status = ClergyValidationStatus.APPROVED
    user.is_verified = True
    user.is_active = True
    update_fields = [
        "pastoral_role",
        "clergy_validation_status",
        "is_verified",
        "is_active",
        "updated_at",
    ]

    # Rattachement territorial dérivé de la paroisse revendiquée, UNIQUEMENT si
    # le compte n'en avait pas : sinon les vues scopées par diocèse resteraient
    # vides pour un clerc dont l'onboarding fidèle n'a jamais été fait. On
    # n'écrase jamais un rattachement existant.
    parish = declaration.parish
    if user.diocese_id is None and parish.diocese_id:
        user.diocese_id = parish.diocese_id
        update_fields.append("diocese_id")
        if user.province_id is None:
            province_id = (
                type(parish).objects.filter(pk=parish.pk)
                .values_list("diocese__province_id", flat=True)
                .first()
            )
            if province_id:
                user.province_id = province_id
                update_fields.append("province_id")

    user.save(update_fields=update_fields)

    # Aucune ``RoleAssignment`` n'est créée : approuver reconnaît une IDENTITÉ
    # pastorale, pas une charge administrative. Nommer un curé titulaire reste un
    # acte explicite, via les endpoints d'affectation de rôle.

    from apps.users.services import _audit

    _audit(
        user,
        AuditEvent.CLERGY_ACCOUNT_APPROVED,
        ip,
        {"performed_by": performed_by.email, "pastoral_role": user.pastoral_role},
    )

    _notify(user, "clergy_account_approved", {"validated_by": performed_by.email})

    return user


@transaction.atomic
def user_reject_clergy_account(
    *,
    user: BaseUser,
    reason: str,
    performed_by: BaseUser,
    ip: str | None = None,
) -> BaseUser:
    """Refuse un compte clergé auto-déclaré. Le motif est obligatoire et notifié."""
    reason = (reason or "").strip()
    if not reason:
        raise ApplicationError("Un motif de refus est obligatoire.")
    if len(reason) > _MAX_REJECTION_REASON_LEN:
        raise ApplicationError(
            f"Le motif de refus ne peut pas dépasser {_MAX_REJECTION_REASON_LEN} caractères."
        )

    declaration = _assert_can_decide(user=user, performed_by=performed_by)

    claimed_role = declaration.claimed_pastoral_role

    declaration.status = ClergySelfDeclaration.Status.REJECTED
    declaration.reviewed_by = performed_by
    declaration.reviewed_at = timezone.now()
    # Le motif est aussi porté par la demande : le demandeur doit pouvoir le lire
    # dans l'application pour corriger et resoumettre. Le journal d'audit reste la
    # trace immuable, mais il ne lui est pas accessible.
    declaration.rejection_reason = reason
    declaration.save(
        update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason", "updated_at"]
    )

    # Défense en profondeur : le rôle clérical n'a jamais dû être posé pendant
    # l'attente, mais on garantit qu'un compte refusé sort laïc quoi qu'il arrive
    # (un compte migré, ou promu par une autre voie, ne doit pas garder la main).
    user.clergy_validation_status = ClergyValidationStatus.REJECTED
    user.pastoral_role = PastoralRole.FIDELE
    user.save(update_fields=["clergy_validation_status", "pastoral_role", "updated_at"])

    from apps.users.services import _audit

    _audit(
        user,
        AuditEvent.CLERGY_ACCOUNT_REJECTED,
        ip,
        {
            "performed_by": performed_by.email,
            "claimed_pastoral_role": claimed_role,
            "reason": reason,
        },
    )

    _notify(user, "clergy_account_rejected", {"reason": reason, "rejected_by": performed_by.email})

    return user

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import ApplicationError
from apps.users.enums import PastoralRole, UserRole
from apps.users.models import BaseUser

from .models import ClergicalInvitation

_INVITATION_EXPIRY_HOURS = 48

# Roles an eveque can invite
_EVEQUE_INVITABLE_ROLES = {PastoralRole.PRETRE, PastoralRole.DIACRE, PastoralRole.RELIGIEUX}

# Roles only super_admin can invite
_SUPER_ADMIN_ONLY_ROLES = {PastoralRole.ARCHEVEQUE, PastoralRole.EVEQUE}


def _can_invite(*, inviter: BaseUser, pastoral_role: str) -> bool:
    if inviter.role == UserRole.SUPER_ADMIN:
        return True
    if pastoral_role in _SUPER_ADMIN_ONLY_ROLES:
        return False
    if inviter.pastoral_role == PastoralRole.ARCHEVEQUE and pastoral_role in _EVEQUE_INVITABLE_ROLES:
        return True
    if inviter.pastoral_role == PastoralRole.EVEQUE and pastoral_role in _EVEQUE_INVITABLE_ROLES:
        return True
    return False


@transaction.atomic
def invitation_create(
    *,
    inviter: BaseUser,
    email: str,
    first_name: str,
    last_name: str,
    pastoral_role: str,
    diocese_id: int | None = None,
) -> ClergicalInvitation:
    if not _can_invite(inviter=inviter, pastoral_role=pastoral_role):
        raise ApplicationError("Vous n'avez pas les droits pour inviter ce type de compte clergé.")

    if ClergicalInvitation.objects.filter(email=email, status=ClergicalInvitation.Status.PENDING).exists():
        raise ApplicationError("Une invitation est déjà en attente pour cette adresse email.")

    expires_at = timezone.now() + timedelta(hours=_INVITATION_EXPIRY_HOURS)

    invitation = ClergicalInvitation.objects.create(
        email=email,
        first_name=first_name,
        last_name=last_name,
        pastoral_role=pastoral_role,
        diocese_id=diocese_id,
        created_by=inviter,
        expires_at=expires_at,
        status=ClergicalInvitation.Status.PENDING,
    )

    transaction.on_commit(lambda: _send_invitation_email(invitation=invitation))

    return invitation


def _send_invitation_email(*, invitation: ClergicalInvitation) -> None:
    from apps.emails.models import Email
    from apps.emails.tasks import email_send as email_send_task

    from django.conf import settings

    frontend_url = getattr(settings, "BASE_FRONTEND_URL", "http://localhost:3000")
    invitation_url = f"{frontend_url}/accept-invitation?token={invitation.token}"

    role_labels = {
        PastoralRole.PRETRE: "Prêtre",
        PastoralRole.DIACRE: "Diacre",
        PastoralRole.RELIGIEUX: "Religieux/Religieuse",
        PastoralRole.EVEQUE: "Évêque",
        PastoralRole.ARCHEVEQUE: "Archevêque",
    }
    role_label = role_labels.get(invitation.pastoral_role, invitation.pastoral_role)

    subject = "[Jàngu Bi] Invitation à rejoindre la plateforme clergé"
    html = (
        f"<p>Bonjour {invitation.first_name} {invitation.last_name},</p>"
        f"<p>Vous avez été invité(e) à rejoindre la plateforme <strong>Jàngu Bi</strong> "
        f"en tant que <strong>{role_label}</strong>.</p>"
        f"<p>Cliquez sur le lien ci-dessous pour créer votre compte :</p>"
        f'<p><a href="{invitation_url}" style="background:#e8c07d;color:#1a1a2e;'
        f'padding:12px 28px;border-radius:6px;text-decoration:none;font-weight:bold;">'
        f"Accepter l'invitation</a></p>"
        f"<p>Ce lien est valable 48 heures.</p>"
        f"<p>Si vous pensez avoir reçu cet email par erreur, vous pouvez l'ignorer.</p>"
    )

    email = Email.objects.create(
        to=invitation.email,
        subject=subject,
        html=html,
        plain_text=html,
        status=Email.Status.SENDING,
    )
    email_send_task.delay(email.id)


@transaction.atomic
def invitation_accept(*, token: str, user: BaseUser) -> ClergicalInvitation:
    try:
        invitation = ClergicalInvitation.objects.select_for_update().get(token=token)
    except ClergicalInvitation.DoesNotExist:
        raise ApplicationError("Invitation introuvable ou invalide.")

    if not invitation.is_valid:
        if invitation.status == ClergicalInvitation.Status.ACCEPTED:
            raise ApplicationError("Cette invitation a déjà été utilisée.")
        if invitation.status == ClergicalInvitation.Status.REVOKED:
            raise ApplicationError("Cette invitation a été révoquée.")
        raise ApplicationError("Cette invitation a expiré.")

    if user.email != invitation.email:
        raise ApplicationError("Cette invitation ne vous est pas destinée.")

    invitation.status = ClergicalInvitation.Status.ACCEPTED
    invitation.accepted_by = user
    invitation.save(update_fields=["status", "accepted_by", "updated_at"])

    user.pastoral_role = invitation.pastoral_role
    if invitation.diocese_id:
        user.diocese_id = invitation.diocese_id
    user.save(update_fields=["pastoral_role", "diocese_id", "updated_at"])

    return invitation


@transaction.atomic
def invitation_revoke(*, invitation: ClergicalInvitation, revoker: BaseUser) -> ClergicalInvitation:
    if invitation.status != ClergicalInvitation.Status.PENDING:
        raise ApplicationError("Seules les invitations en attente peuvent être révoquées.")

    invitation.status = ClergicalInvitation.Status.REVOKED
    invitation.save(update_fields=["status", "updated_at"])

    return invitation

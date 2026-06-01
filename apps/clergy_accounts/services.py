from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import ApplicationError
from apps.users.enums import PastoralRole, RoleScope, UserRole
from apps.users.models import BaseUser
from apps.users.services_roles import role_assignment_create

from .models import ClergicalInvitation

_INVITATION_EXPIRY_HOURS = 48

# Rôles qu'un évêque/archevêque peut inviter.
_EVEQUE_INVITABLE_ROLES = {PastoralRole.PRETRE, PastoralRole.DIACRE, PastoralRole.RELIGIEUX}

# Rôles que seul un super_admin peut inviter.
_SUPER_ADMIN_ONLY_ROLES = {PastoralRole.ARCHEVEQUE, PastoralRole.EVEQUE}

# Évêque/archevêque = autorité pastorale habilitée à inviter du clergé.
_BISHOP_PASTORAL_ROLES = {PastoralRole.EVEQUE, PastoralRole.ARCHEVEQUE}


def _can_invite(*, inviter: BaseUser, pastoral_role: str) -> bool:
    """Qui peut inviter quel rôle pastoral.

    Règle unique (alignée avec ``_can_manage_invitations`` côté API) :
    - super_admin → tout, y compris évêque/archevêque ;
    - évêque/archevêque → prêtre / diacre / religieux uniquement.
    """
    if inviter.role == UserRole.SUPER_ADMIN:
        return True
    # Seul le super_admin invite un évêque/archevêque.
    if pastoral_role in _SUPER_ADMIN_ONLY_ROLES:
        return False
    return (
        inviter.pastoral_role in _BISHOP_PASTORAL_ROLES
        and pastoral_role in _EVEQUE_INVITABLE_ROLES
    )


def _validate_and_authorize_target(
    *, inviter: BaseUser, parish_id: int | None, church_id: int | None, diocese_id: int | None
) -> None:
    """Valide l'existence des cibles ET l'autorité territoriale de l'invitant.

    Source de vérité = RoleAssignment (via scoping.py). Empêche un évêque du
    diocèse X de planter une capacité scopée (parish_admin/diocese_admin) dans
    une paroisse/diocèse hors de son territoire. Le super_admin (admin global)
    passe partout.
    """
    from apps.org.models import Church, Diocese, Parish
    from apps.users.scoping import user_can_admin_diocese, user_can_admin_parish

    if parish_id is not None:
        if not Parish.objects.filter(pk=parish_id).exists():
            raise ApplicationError("Paroisse cible introuvable.")
        if not user_can_admin_parish(inviter, parish_id):
            raise ApplicationError("Vous n'avez pas autorité sur cette paroisse.")

    if church_id is not None:
        church = Church.objects.filter(pk=church_id).first()
        if church is None:
            raise ApplicationError("Église cible introuvable.")
        if not user_can_admin_parish(inviter, church.parish_id):
            raise ApplicationError("Vous n'avez pas autorité sur cette église.")

    if diocese_id is not None:
        if not Diocese.objects.filter(pk=diocese_id).exists():
            raise ApplicationError("Diocèse cible introuvable.")
        if not user_can_admin_diocese(inviter, diocese_id):
            raise ApplicationError("Vous n'avez pas autorité sur ce diocèse.")


@transaction.atomic
def invitation_create(
    *,
    inviter: BaseUser,
    email: str,
    first_name: str,
    last_name: str,
    pastoral_role: str,
    diocese_id: int | None = None,
    parish_id: int | None = None,
    church_id: int | None = None,
) -> ClergicalInvitation:
    if not _can_invite(inviter=inviter, pastoral_role=pastoral_role):
        raise ApplicationError("Vous n'avez pas les droits pour inviter ce type de compte clergé.")

    if ClergicalInvitation.objects.filter(email=email, status=ClergicalInvitation.Status.PENDING).exists():
        raise ApplicationError("Une invitation est déjà en attente pour cette adresse email.")

    _validate_and_authorize_target(
        inviter=inviter, parish_id=parish_id, church_id=church_id, diocese_id=diocese_id
    )

    expires_at = timezone.now() + timedelta(hours=_INVITATION_EXPIRY_HOURS)

    invitation = ClergicalInvitation.objects.create(
        email=email,
        first_name=first_name,
        last_name=last_name,
        pastoral_role=pastoral_role,
        diocese_id=diocese_id,
        parish_id=parish_id,
        church_id=church_id,
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


def _resolve_capacity(invitation: ClergicalInvitation) -> tuple[dict | None, int | None]:
    """Dérive la capacité administrative (RoleAssignment) + le diocèse de
    rattachement depuis ``pastoral_role`` et la cible territoriale.

    Retourne ``(kwargs role_assignment_create | None, diocese_id | None)``.
    Sans cible exploitable, la capacité est ``None`` : le compte est tout de
    même activé (pastoral_role), mais aucune affectation scopée n'est créée.
    """
    role = invitation.pastoral_role

    if role == PastoralRole.PRETRE and invitation.parish_id:
        parish = invitation.parish
        return (
            {"role": UserRole.PARISH_ADMIN, "scope": RoleScope.PARISH,
             "parish": parish, "is_principal": True},
            parish.diocese_id,
        )

    if role == PastoralRole.DIACRE and invitation.church_id:
        church = invitation.church
        return (
            {"role": UserRole.CHURCH_ADMIN, "scope": RoleScope.CHURCH,
             "church": church, "is_principal": False},
            church.parish.diocese_id,
        )

    if role == PastoralRole.DIACRE and invitation.parish_id:
        parish = invitation.parish
        return (
            {"role": UserRole.PARISH_ADMIN, "scope": RoleScope.PARISH,
             "parish": parish, "is_principal": False},
            parish.diocese_id,
        )

    if role == PastoralRole.EVEQUE and invitation.diocese_id:
        return (
            {"role": UserRole.DIOCESE_ADMIN, "scope": RoleScope.DIOCESE,
             "diocese": invitation.diocese, "is_principal": True},
            invitation.diocese_id,
        )

    if role == PastoralRole.ARCHEVEQUE and invitation.diocese_id:
        return (
            {"role": UserRole.PROVINCE_ADMIN, "scope": RoleScope.PROVINCE,
             "province": invitation.diocese.province, "is_principal": True},
            invitation.diocese_id,
        )

    # Religieux ou rôle sans cible exploitable : pas de capacité scopée.
    return (None, invitation.diocese_id)


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

    ra_kwargs, diocese_id = _resolve_capacity(invitation)

    # Accepter une invitation clergé vérifie et active le compte.
    user.pastoral_role = invitation.pastoral_role
    user.is_verified = True
    user.is_active = True
    update_fields = ["pastoral_role", "is_verified", "is_active", "updated_at"]
    if diocese_id:
        from apps.org.models import Diocese

        user.diocese_id = diocese_id
        update_fields.append("diocese_id")
        # Province dérivée du diocèse — cohérence avec le signal territorial des
        # fidèles (qui remplit diocese ET province). Sinon archevêque/évêque
        # créés par invitation gardaient province=NULL.
        province_id = (
            Diocese.objects.filter(id=diocese_id)
            .values_list("province_id", flat=True)
            .first()
        )
        if province_id:
            user.province_id = province_id
            update_fields.append("province_id")
    user.save(update_fields=update_fields)

    # Capacité administrative scopée (curé → parish_admin principal, etc.).
    if ra_kwargs is not None:
        role_assignment_create(user=user, granted_by=invitation.created_by, **ra_kwargs)

    return invitation


@transaction.atomic
def invitation_revoke(*, invitation: ClergicalInvitation, revoker: BaseUser) -> ClergicalInvitation:
    if invitation.status != ClergicalInvitation.Status.PENDING:
        raise ApplicationError("Seules les invitations en attente peuvent être révoquées.")

    invitation.status = ClergicalInvitation.Status.REVOKED
    invitation.save(update_fields=["status", "updated_at"])

    return invitation

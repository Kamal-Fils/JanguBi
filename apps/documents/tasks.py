from celery import shared_task
from django.utils import timezone


@shared_task(bind=True, max_retries=3)
def document_requests_auto_escalate(self):
    from datetime import timedelta

    from django.conf import settings

    from apps.documents.models import DocumentRequest
    from apps.documents.services import _send_email

    escalate_days = getattr(settings, "DOCS_ESCALATE_DAYS", 7)
    deposit_reminder_days = getattr(settings, "DOCS_DEPOSIT_REMINDER_DAYS", 3)
    requester_reminder_days = getattr(settings, "DOCS_REQUESTER_REMINDER_DAYS", 5)
    now = timezone.now()

    try:
        # SUBMITTED bloquée → rappel fidèle + agents
        for req in DocumentRequest.objects.filter(
            status=DocumentRequest.Status.SUBMITTED,
            updated_at__lt=now - timedelta(days=escalate_days),
        ).select_related("assigned_to", "requester"):
            _send_email(
                to=req.contact_email,
                subject=f"[Jàngu Bi] Votre demande {req.reference} est en attente",
                body_html=(
                    f"<p>Bonjour {req.requester_first_names},</p>"
                    f"<p>Votre demande <strong>{req.reference}</strong> est en attente de traitement "
                    f"depuis plus de {escalate_days} jours.</p>"
                ),
            )
            for agent in _agent_recipients(req):
                _send_email(
                    to=agent.email,
                    subject=f"[Jàngu Bi] Demande en attente — {req.reference}",
                    body_html=(
                        f"<p>La demande <strong>{req.reference}</strong> est soumise depuis plus de "
                        f"{escalate_days} jours sans prise en charge.</p>"
                    ),
                )

        # UNDER_VERIFICATION bloquée → rappel agent
        for req in DocumentRequest.objects.filter(
            status=DocumentRequest.Status.UNDER_VERIFICATION,
            updated_at__lt=now - timedelta(days=escalate_days),
        ).select_related("assigned_to"):
            for agent in _agent_recipients(req):
                _send_email(
                    to=agent.email,
                    subject=f"[Jàngu Bi] Vérification en attente — {req.reference}",
                    body_html=(
                        f"<p>La demande <strong>{req.reference}</strong> est en vérification depuis "
                        f"plus de {escalate_days} jours.</p>"
                    ),
                )

        # VALIDATED sans dépôt → rappel agent
        for req in DocumentRequest.objects.filter(
            status=DocumentRequest.Status.VALIDATED,
            updated_at__lt=now - timedelta(days=deposit_reminder_days),
        ).select_related("assigned_to"):
            for agent in _agent_recipients(req):
                _send_email(
                    to=agent.email,
                    subject=f"[Jàngu Bi] Rappel dépôt — {req.reference}",
                    body_html=(
                        f"<p>La demande <strong>{req.reference}</strong> est validée depuis plus de "
                        f"{deposit_reminder_days} jours. Merci de déposer le document final.</p>"
                    ),
                )

        # INFO_REQUESTED sans réponse → rappel fidèle
        for req in DocumentRequest.objects.filter(
            status=DocumentRequest.Status.INFO_REQUESTED,
            updated_at__lt=now - timedelta(days=requester_reminder_days),
        ).select_related("requester"):
            _send_email(
                to=req.contact_email,
                subject=f"[Jàngu Bi] Rappel complément — {req.reference}",
                body_html=(
                    f"<p>Bonjour {req.requester_first_names},</p>"
                    f"<p>Nous attendons toujours votre complément pour la demande "
                    f"<strong>{req.reference}</strong>. Merci de répondre dans les meilleurs délais.</p>"
                ),
            )

    except Exception as exc:
        self.retry(exc=exc, countdown=3600)


def _agent_recipients(request_obj):
    from apps.users.enums import UserRole
    from apps.users.models import BaseUser

    _AGENT_ROLES = {
        UserRole.PARISH_ADMIN,
        UserRole.CHURCH_ADMIN,
        UserRole.DIOCESE_ADMIN,
        UserRole.PROVINCE_ADMIN,
        UserRole.SUPER_ADMIN,
    }
    if request_obj.assigned_to_id:
        return [request_obj.assigned_to]
    return list(BaseUser.objects.filter(role__in=list(_AGENT_ROLES), is_active=True)[:20])

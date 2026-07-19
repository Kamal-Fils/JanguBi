from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

# Nombre maximal de tentatives d'envoi avant abandon définitif.
# Sans borne, une panne SMTP durable ferait boucler la tâche indéfiniment :
# la file RabbitMQ sature et affame les autres tâches (escalade documents,
# purge des conversations).
EMAIL_SEND_MAX_RETRIES = 5

# Backoff exponentiel : 60 s, 120 s, 240 s, 480 s, 600 s (plafonné).
EMAIL_SEND_RETRY_BASE_DELAY = 60
EMAIL_SEND_RETRY_MAX_DELAY = 600


def _retry_countdown(retries: int) -> int:
    """Délai avant la prochaine tentative — exponentiel, plafonné."""
    return min(EMAIL_SEND_RETRY_BASE_DELAY * (2**retries), EMAIL_SEND_RETRY_MAX_DELAY)


def _email_send_failure(self, exc, task_id, args, kwargs, einfo):
    """Bascule l'Email en FAILED quand la tâche a épuisé ses tentatives.

    Ce handler doit être TOTALEMENT défensif : toute exception levée ici
    remplacerait la trace de l'erreur d'origine et laisserait l'Email bloqué
    en SENDING pour toujours. Les trois cas gardés :
      - `args` vide (tâche appelée en kwargs) ;
      - l'Email a été supprimé entre la mise en file et l'échec ;
      - l'Email n'est plus en SENDING (email_failed lève ApplicationError).
    """
    from apps.emails.models import Email  # local import — évite les imports circulaires
    from apps.emails.services import email_failed

    email_id = args[0] if args else kwargs.get("email_id")
    if email_id is None:
        logger.error("email_send failure handler: aucun email_id dans args/kwargs (task_id=%s)", task_id)
        return

    try:
        email = Email.objects.get(id=email_id)
    except Email.DoesNotExist:
        logger.warning("email_send failure handler: Email %s introuvable (supprimé ?)", email_id)
        return

    try:
        email_failed(email)
    except Exception:  # noqa: BLE001 — le handler ne doit JAMAIS propager
        logger.exception("email_send failure handler: impossible de marquer l'Email %s en FAILED", email_id)


@shared_task(bind=True, max_retries=EMAIL_SEND_MAX_RETRIES, on_failure=_email_send_failure)
def email_send(self, email_id):
    from apps.emails.models import Email  # local import — évite les imports circulaires
    from apps.emails.services import email_send as email_send_service

    email = Email.objects.get(id=email_id)

    try:
        email_send_service(email)
    except Exception as exc:
        # https://docs.celeryq.dev/en/stable/userguide/tasks.html#retrying
        # Tentatives bornées + backoff exponentiel : au-delà, la tâche échoue
        # définitivement et `_email_send_failure` bascule l'Email en FAILED.
        countdown = _retry_countdown(self.request.retries)
        logger.warning(
            "Exception occurred while sending email %s (tentative %s/%s, prochaine dans %ss): %s",
            email_id,
            self.request.retries + 1,
            EMAIL_SEND_MAX_RETRIES,
            countdown,
            exc,
        )
        raise self.retry(exc=exc, countdown=countdown)

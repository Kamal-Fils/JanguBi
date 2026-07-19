import logging
import uuid
from datetime import date

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import ApplicationError

from .models import MassIntention, MassIntentionStatus, MassIntentionStatusLog

logger = logging.getLogger(__name__)

# Libellés lisibles réutilisés par les e-mails ET le reçu PDF : une seule
# traduction statut/type → français, pour que le reçu ne puisse pas diverger de
# ce que le fidèle a lu dans sa boîte mail.
_TYPE_LABELS = dict(MassIntention._meta.get_field("intention_type").choices or [])
_STATUS_LABELS = dict(MassIntention._meta.get_field("status").choices or [])


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------


def _log_status_change(
    *,
    intention: MassIntention,
    from_status: str,
    to_status: str,
    changed_by=None,
    comment: str = "",
) -> MassIntentionStatusLog:
    return MassIntentionStatusLog.objects.create(
        intention=intention,
        from_status=from_status,
        to_status=to_status,
        changed_by=changed_by,
        comment=comment,
    )


def _send_email(*, to: str, subject: str, body_html: str) -> None:
    """Dispatch e-mail via le modèle ``Email`` (jamais de SMTP direct).

    L'envoi part sur ``transaction.on_commit`` : si la transaction de la
    transition échoue après coup, aucun e-mail n'annonce un changement qui n'a
    pas eu lieu.
    """
    from apps.emails.models import Email
    from apps.emails.tasks import email_send as email_send_task

    email = Email.objects.create(
        to=to,
        subject=subject,
        html=body_html,
        plain_text=body_html,
        status=Email.Status.SENDING,
    )
    transaction.on_commit(lambda: email_send_task.delay(email.id))


def _notify_requestor(*, intention: MassIntention, event: str, extra: str = "") -> None:
    """Informe le fidèle à chaque transition.

    Le front annonçait déjà « Le fidèle sera informé » à chaque action du
    clergé, alors qu'aucun e-mail n'était envoyé nulle part dans cette app :
    la promesse était vide. Elle est tenue ici.
    """
    to = getattr(intention.requestor, "email", None)
    if not to:
        return

    ref = intention.reference
    subjects = {
        "accepted": f"[Jàngu Bi] Intention acceptée — {ref}",
        "date_proposed": f"[Jàngu Bi] Date proposée — {ref}",
        "confirmed": f"[Jàngu Bi] Date confirmée — {ref}",
        "celebrated": f"[Jàngu Bi] Messe célébrée — {ref}",
        "declined": f"[Jàngu Bi] Intention non retenue — {ref}",
    }
    bodies = {
        "accepted": (
            f"<p>Votre intention de messe <strong>{ref}</strong> a été acceptée "
            f"par votre paroisse. Une date de célébration vous sera proposée.</p>"
        ),
        "date_proposed": (
            f"<p>Une date de célébration est proposée pour votre intention "
            f"<strong>{ref}</strong> : <strong>{extra}</strong>.</p>"
            f"<p>Vous pouvez confirmer cette date depuis l'application.</p>"
        ),
        "confirmed": (
            f"<p>La date de célébration de votre intention <strong>{ref}</strong> "
            f"est confirmée : <strong>{extra}</strong>.</p>"
        ),
        "celebrated": (
            f"<p>La messe a été célébrée à votre intention <strong>{ref}</strong>"
            f"{f' le <strong>{extra}</strong>' if extra else ''}.</p>"
            f"<p>Votre reçu numérique est disponible dans l'application.</p>"
        ),
        "declined": (
            f"<p>Votre intention <strong>{ref}</strong> n'a pas pu être retenue.</p>"
            f"{f'<p>{extra}</p>' if extra else ''}"
        ),
    }
    subject = subjects.get(event)
    body = bodies.get(event)
    if not subject or not body:
        return
    _send_email(to=to, subject=subject, body_html=body)


def _assert_parish_authority(*, intention: MassIntention, pretre) -> None:
    """Garde territoriale des actions de traitement (RG-SEC).

    Le contrôle de rôle fait en amont dans ``apis.py`` est **global** : il dit
    « c'est un prêtre », pas « c'est LE prêtre de cette paroisse ». Sans cette
    garde, n'importe quel prêtre du pays pouvait accepter/refuser/dater/célébrer
    l'intention d'un fidèle d'une autre paroisse — et lire au passage
    ``intention_text``, qui contient souvent une confidence personnelle.

    On lève une ``ApplicationError`` (et non ``Http404``) parce qu'on est dans
    la couche service : elle doit rester sûre même appelée hors HTTP (tâche
    Celery, commande de gestion, futur endpoint) et ne doit pas connaître les
    exceptions HTTP. Le non-dévoilement d'existence est déjà assuré en amont
    par ``mass_intention_get``, qui lève ``Http404``.

    Fail-closed : périmètre vide, ou intention sans paroisse, → refus (sauf
    admin global). Le message ne nomme jamais la paroisse d'autrui.
    """
    from .selectors import pretre_accessible_parish_ids

    parish_ids = pretre_accessible_parish_ids(user=pretre)
    if parish_ids is None:  # admin global — autorité sur tout le territoire
        return
    if intention.parish_id is None or intention.parish_id not in parish_ids:
        raise ApplicationError("Vous n'avez pas autorité sur la paroisse de cette intention.")


def _assert_can_confirm(*, intention: MassIntention, user) -> str:
    """Qui peut confirmer la date proposée — et à quel titre.

    Deux acteurs légitimes, pour deux réalités pastorales distinctes :

    * le **fidèle demandeur**, qui accepte la date qu'on lui propose : c'est le
      chemin nominal du SRS (``date_proposed → confirmed``) ;
    * le **clergé ayant autorité territoriale**, qui acte un accord donné de
      vive voix (au presbytère, par téléphone) — cas courant au Sénégal, où
      beaucoup de fidèles n'ouvriront jamais l'app pour cliquer.

    Toute autre personne est refusée, y compris un membre du clergé hors de son
    périmètre : la confirmation fixe la date d'une messe, ce n'est pas un acte
    anodin. Renvoie l'acteur (« requestor » / « clergy ») pour que le journal
    garde la trace du titre auquel la confirmation a été faite.
    """
    if intention.requestor_id == getattr(user, "id", None):
        return "requestor"

    from .selectors import CLERGY_PASTORAL_ROLES, pretre_accessible_parish_ids

    is_clergy = getattr(user, "pastoral_role", None) in CLERGY_PASTORAL_ROLES
    parish_ids = pretre_accessible_parish_ids(user=user)
    # ``None`` = admin global : autorité sur tout le territoire.
    if parish_ids is None:
        return "clergy"
    if is_clergy and intention.parish_id is not None and intention.parish_id in parish_ids:
        return "clergy"

    raise ApplicationError(
        "Seul le fidèle demandeur ou un prêtre de sa paroisse peut confirmer cette date."
    )


# ---------------------------------------------------------------------------
# Reçu numérique
# ---------------------------------------------------------------------------


def _render_receipt_pdf(*, intention: MassIntention) -> bytes:
    """Compose le PDF du reçu **à partir des seules données stockées**.

    Aucun paramètre client n'entre ici : ni le nom du célébrant, ni la date, ni
    la paroisse. Un fidèle ne peut donc pas se fabriquer un reçu portant une
    date ou un prêtre de son choix en jouant sur le corps de la requête — le
    contenu est une projection de la ligne en base, rien d'autre.

    Même mécanique que l'export de conversation (``apps/messaging/services.py``)
    : reportlab ``canvas`` → octets, puis stockage dans un ``File``.
    """
    import io

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    def _fr_date(value: date | None) -> str:
        return value.strftime("%d/%m/%Y") if value else "—"

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(25 * mm, height - 30 * mm, "Reçu d'intention de messe")

    pdf.setFont("Helvetica", 10)
    pdf.drawString(25 * mm, height - 38 * mm, "Jàngu Bi — plateforme communautaire catholique")
    pdf.line(25 * mm, height - 42 * mm, width - 25 * mm, height - 42 * mm)

    parish = intention.parish
    parish_name = parish.name if parish is not None else "—"
    celebrant = getattr(intention.pretre, "email", None) or "—"
    requestor = getattr(intention.requestor, "email", None) or "—"

    rows = [
        ("Référence", intention.reference),
        ("Demandeur", requestor),
        ("Type d'intention", str(_TYPE_LABELS.get(intention.intention_type, intention.intention_type))),
        ("Paroisse", parish_name),
        ("Célébrant", celebrant),
        ("Date de célébration", _fr_date(intention.celebration_date)),
        ("Statut", str(_STATUS_LABELS.get(intention.status, intention.status))),
    ]

    y = height - 55 * mm
    for label, value in rows:
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(25 * mm, y, f"{label}")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(70 * mm, y, str(value)[:70])
        y -= 8 * mm

    y -= 4 * mm
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(25 * mm, y, "Intention confiée")
    y -= 7 * mm
    pdf.setFont("Helvetica", 10)
    # Découpe simple : le texte d'intention est libre et peut être long.
    text = " ".join((intention.intention_text or "").split())
    for start in range(0, min(len(text), 900), 90):
        if y < 30 * mm:
            pdf.showPage()
            y = height - 30 * mm
            pdf.setFont("Helvetica", 10)
        pdf.drawString(25 * mm, y, text[start : start + 90])
        y -= 6 * mm

    pdf.setFont("Helvetica-Oblique", 8)
    pdf.drawString(
        25 * mm,
        20 * mm,
        f"Émis le {timezone.now().strftime('%d/%m/%Y à %H:%M')} — document généré automatiquement.",
    )

    pdf.save()
    buffer.seek(0)
    return buffer.read()


def _build_receipt_file(*, intention: MassIntention):
    """Matérialise le PDF du reçu dans un ``File`` valide.

    ``upload_finished_at`` est posé explicitement : sans lui le fichier reste
    « invalide » au sens de ``File.is_valid`` et ne doit pas être servi.
    """
    from django.core.files.base import ContentFile

    from apps.files.models import File

    pdf_bytes = _render_receipt_pdf(intention=intention)
    filename = f"recu_{intention.reference}.pdf"

    file_obj = File.objects.create(
        original_file_name=filename,
        file_name=f"{uuid.uuid4()}_{filename}",
        file_type="application/pdf",
    )
    file_obj.file.save(file_obj.file_name, ContentFile(pdf_bytes), save=True)
    file_obj.upload_finished_at = timezone.now()
    file_obj.save(update_fields=["upload_finished_at"])
    return file_obj


@transaction.atomic
def mass_intention_receipt_ensure(*, intention: MassIntention) -> MassIntention:
    """Garantit qu'un reçu téléchargeable existe — **rejouable**.

    Le fidèle doit pouvoir revenir chercher son reçu des mois plus tard (perte
    du mail, changement de téléphone). Si le fichier existe déjà on le renvoie
    tel quel — on ne réémet pas un document différent à chaque clic, la
    référence et le contenu restent stables. On ne (re)génère que si le reçu
    manque : intention célébrée avant l'existence de cette fonctionnalité, ou
    fichier perdu côté stockage.

    Refuse toute intention non célébrée : un reçu atteste d'une messe dite.
    """
    if intention.status != MassIntentionStatus.CELEBRATED:
        raise ApplicationError(
            "Le reçu n'est disponible qu'une fois la messe célébrée."
        )

    existing = intention.receipt_file
    if existing is not None and existing.is_valid:
        return intention

    intention.receipt_file = _build_receipt_file(intention=intention)
    intention.save(update_fields=["receipt_file", "updated_at"])
    return intention


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------


@transaction.atomic
def mass_intention_submit(
    *,
    requestor,
    intention_type: str,
    intention_text: str,
    parish=None,
) -> MassIntention:
    # B6b : défaut = paroisse PRINCIPALE du demandeur (appartenance is_primary),
    # repli legacy sur primary_parish ; jamais None.
    if parish is None:
        from apps.users.models import Membership

        primary = (
            Membership.objects.filter(user=requestor, is_primary=True)
            .select_related("church__parish")
            .first()
        )
        if primary is not None:
            parish = primary.church.parish
        else:
            parish = getattr(getattr(requestor, "profile", None), "primary_parish", None)
    if parish is None:
        raise ApplicationError(
            "Aucune paroisse : précisez la paroisse ou définissez votre paroisse principale."
        )

    intention = MassIntention.objects.create(
        requestor=requestor,
        intention_type=intention_type,
        intention_text=intention_text,
        parish=parish,
    )
    _log_status_change(
        intention=intention,
        from_status="",
        to_status=MassIntentionStatus.PENDING,
        changed_by=requestor,
        comment="Intention soumise.",
    )
    return intention


@transaction.atomic
def mass_intention_accept(*, intention: MassIntention, pretre) -> MassIntention:
    _assert_parish_authority(intention=intention, pretre=pretre)
    if intention.status != MassIntentionStatus.PENDING:
        raise ApplicationError("Cette intention n'est pas en attente d'acceptation.")
    prev_status = intention.status
    intention.pretre = pretre
    intention.status = MassIntentionStatus.ACCEPTED
    intention.save(update_fields=["pretre", "status", "updated_at"])
    _log_status_change(
        intention=intention,
        from_status=prev_status,
        to_status=MassIntentionStatus.ACCEPTED,
        changed_by=pretre,
    )
    _notify_requestor(intention=intention, event="accepted")
    return intention


@transaction.atomic
def mass_intention_propose_date(
    *, intention: MassIntention, proposed_date, pretre
) -> MassIntention:
    _assert_parish_authority(intention=intention, pretre=pretre)
    if intention.status not in (MassIntentionStatus.ACCEPTED, MassIntentionStatus.CONFIRMED):
        raise ApplicationError("Cette intention doit être acceptée avant de proposer une date.")
    prev_status = intention.status
    intention.proposed_date = proposed_date
    intention.status = MassIntentionStatus.DATE_PROPOSED
    intention.save(update_fields=["proposed_date", "status", "updated_at"])
    _log_status_change(
        intention=intention,
        from_status=prev_status,
        to_status=MassIntentionStatus.DATE_PROPOSED,
        changed_by=pretre,
        comment=f"Date proposée : {proposed_date}",
    )
    _notify_requestor(
        intention=intention, event="date_proposed", extra=str(proposed_date)
    )
    return intention


@transaction.atomic
def mass_intention_confirm_date(*, intention: MassIntention, user) -> MassIntention:
    """``date_proposed → confirmed`` — le chaînon manquant du cycle SRS.

    Le statut ``CONFIRMED`` existait dans l'énumération et était accepté comme
    statut de DÉPART par ``propose_date`` et ``celebrate``, mais aucune
    transition ne l'atteignait : il était inatteignable. Le fidèle n'avait donc
    aucun moyen d'accepter la date qu'on lui proposait, et la boucle
    « proposition → accord » restait ouverte.

    Fige la date : ``celebration_date`` prend la valeur de ``proposed_date``,
    ce qui rend l'accord opposable même si une date est reproposée ensuite.
    """
    actor = _assert_can_confirm(intention=intention, user=user)

    if intention.status != MassIntentionStatus.DATE_PROPOSED:
        raise ApplicationError(
            "Aucune date en attente de confirmation pour cette intention."
        )
    if intention.proposed_date is None:
        # Défense en profondeur : un statut date_proposed sans date serait une
        # incohérence de données, pas une confirmation valide.
        raise ApplicationError("Aucune date proposée à confirmer.")

    prev_status = intention.status
    intention.status = MassIntentionStatus.CONFIRMED
    intention.celebration_date = intention.proposed_date
    intention.save(update_fields=["status", "celebration_date", "updated_at"])
    _log_status_change(
        intention=intention,
        from_status=prev_status,
        to_status=MassIntentionStatus.CONFIRMED,
        changed_by=user,
        comment=(
            f"Date confirmée : {intention.celebration_date}"
            f"{' (par la paroisse)' if actor == 'clergy' else ''}"
        ),
    )
    _notify_requestor(
        intention=intention, event="confirmed", extra=str(intention.celebration_date)
    )
    return intention


@transaction.atomic
def mass_intention_celebrate(
    *, intention: MassIntention, pretre, celebration_date=None
) -> MassIntention:
    """Clôt le cycle : messe célébrée + émission du reçu numérique.

    ``celebration_date`` n'était jamais renseignée : la colonne existait, le
    sérialiseur l'exposait et le front affichait « Célébrée le », mais rien ne
    l'écrivait — la date affichée était donc toujours vide. Elle est désormais
    posée explicitement (date fournie par le prêtre, à défaut la date confirmée
    ou proposée, à défaut aujourd'hui).
    """
    _assert_parish_authority(intention=intention, pretre=pretre)
    if intention.status not in (
        MassIntentionStatus.ACCEPTED,
        MassIntentionStatus.DATE_PROPOSED,
        MassIntentionStatus.CONFIRMED,
    ):
        raise ApplicationError("Cette intention n'est pas dans un état permettant la célébration.")

    prev_status = intention.status
    intention.status = MassIntentionStatus.CELEBRATED
    intention.celebration_date = (
        celebration_date
        or intention.celebration_date
        or intention.proposed_date
        or timezone.localdate()
    )
    # Le prêtre qui célèbre est le célébrant porté sur le reçu : sans cela une
    # intention célébrée directement depuis « pending » n'aurait aucun célébrant.
    if intention.pretre_id is None:
        intention.pretre = pretre
    intention.save(update_fields=["status", "celebration_date", "pretre", "updated_at"])

    _log_status_change(
        intention=intention,
        from_status=prev_status,
        to_status=MassIntentionStatus.CELEBRATED,
        changed_by=pretre,
        comment=f"Célébrée le {intention.celebration_date}",
    )

    # Le reçu est émis dans la foulée, mais son échec ne doit JAMAIS annuler la
    # célébration : le fait pastoral (la messe a été dite) prime sur son
    # justificatif. Sans ce point de reprise, une indisponibilité du stockage
    # objet (MinIO/S3 injoignable) faisait remonter une 500 et le prêtre perdait
    # l'enregistrement de la célébration — on troquait l'essentiel contre
    # l'accessoire.
    #
    # Le bloc atomique imbriqué pose un point de sauvegarde : si l'écriture du
    # fichier échoue, la ligne ``File`` déjà créée est annulée avec lui (pas de
    # fichier fantôme sans contenu), et la transition, elle, est conservée.
    # L'échec est journalisé — jamais avalé — et le reçu reste régénérable à la
    # demande via ``mass_intention_receipt_ensure`` (endpoint dédié).
    try:
        with transaction.atomic():
            mass_intention_receipt_ensure(intention=intention)
    except Exception:
        logger.exception(
            "Reçu non émis pour l'intention %s : la célébration est enregistrée, "
            "le reçu sera régénéré à la première demande.",
            intention.reference,
        )

    _notify_requestor(
        intention=intention, event="celebrated", extra=str(intention.celebration_date)
    )
    return intention


@transaction.atomic
def mass_intention_decline(
    *, intention: MassIntention, pretre, notes: str = ""
) -> MassIntention:
    _assert_parish_authority(intention=intention, pretre=pretre)
    if intention.status not in (MassIntentionStatus.PENDING, MassIntentionStatus.ACCEPTED):
        raise ApplicationError("Cette intention ne peut pas être refusée dans son état actuel.")
    prev_status = intention.status
    intention.status = MassIntentionStatus.DECLINED
    intention.notes = notes
    intention.save(update_fields=["status", "notes", "updated_at"])
    _log_status_change(
        intention=intention,
        from_status=prev_status,
        to_status=MassIntentionStatus.DECLINED,
        changed_by=pretre,
        comment=notes,
    )
    _notify_requestor(intention=intention, event="declined", extra=notes)
    return intention

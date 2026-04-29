import io
import json

from celery import shared_task
from django.utils import timezone


@shared_task(bind=True, max_retries=3)
def purge_expired_conversations(self):
    from apps.messaging.models import Conversation, Message

    now = timezone.now()
    expired = Conversation.objects.filter(
        scheduled_purge_at__lt=now,
        scheduled_purge_at__isnull=False,
    )

    for conversation in expired:
        try:
            if not conversation.exports.filter(completed_at__isnull=False).exists():
                generate_conversation_export.delay(None, conversation_id=str(conversation.id))

            Message.objects.filter(conversation=conversation).update(
                content="",
                deleted_at=now,
            )
            conversation.scheduled_purge_at = None
            conversation.save(update_fields=["scheduled_purge_at", "updated_at"])
        except Exception as exc:
            self.retry(exc=exc, countdown=3600)


@shared_task(bind=True, max_retries=3)
def notify_purge_upcoming(self):
    from datetime import timedelta

    from apps.messaging.models import Conversation
    from apps.messaging.services import notification_send

    warning_threshold = timezone.now() + timedelta(days=7)
    upcoming = Conversation.objects.filter(
        scheduled_purge_at__lte=warning_threshold,
        scheduled_purge_at__gt=timezone.now(),
    ).select_related("participant_a", "participant_b")

    for conversation in upcoming:
        payload = {
            "conversation_id": str(conversation.id),
            "purge_date": conversation.scheduled_purge_at.date().isoformat(),
        }
        for user in [conversation.participant_a, conversation.participant_b]:
            try:
                notification_send(
                    user=user,
                    event_type="conversation.purge_upcoming",
                    payload=payload,
                )
            except Exception:
                pass


@shared_task(bind=True, max_retries=3)
def generate_conversation_export(self, export_id, conversation_id=None):
    from apps.messaging.models import Conversation, ConversationExport, Message
    from apps.messaging.serializers import MessageOutputSerializer

    try:
        if export_id:
            export = ConversationExport.objects.select_related("conversation").get(id=export_id)
            conversation = export.conversation
        else:
            conversation = Conversation.objects.get(id=conversation_id)
            export = ConversationExport.objects.create(conversation=conversation)

        messages = Message.objects.filter(conversation=conversation).order_by("created_at")
        export_data = {
            "conversation_id": str(conversation.id),
            "exported_at": timezone.now().isoformat(),
            "messages": MessageOutputSerializer(messages, many=True).data,
        }

        json_bytes = json.dumps(export_data, ensure_ascii=False, default=str).encode("utf-8")
        pdf_bytes = _generate_pdf(export_data)

        export.json_file = _upload_file(
            content=json_bytes,
            filename=f"export_{conversation.id}.json",
            content_type="application/json",
        )
        export.pdf_file = _upload_file(
            content=pdf_bytes,
            filename=f"export_{conversation.id}.pdf",
            content_type="application/pdf",
        )
        export.completed_at = timezone.now()
        export.save(update_fields=["json_file", "pdf_file", "completed_at", "updated_at"])

    except Exception as exc:
        self.retry(exc=exc, countdown=60)


def _generate_pdf(data: dict) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 50, f"Export — {data['conversation_id']}")
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 70, f"Exporté le : {data['exported_at']}")

    y = height - 110
    c.setFont("Helvetica", 9)
    for msg in data.get("messages", []):
        if y < 60:
            c.showPage()
            y = height - 50
        sender = msg.get("sender_name", "?")
        content = msg.get("content") or "[message supprimé]"
        created = str(msg.get("created_at", ""))[:19]
        c.drawString(50, y, f"[{created}] {sender}: {content}"[:120])
        y -= 15

    c.save()
    buffer.seek(0)
    return buffer.read()


def _upload_file(*, content: bytes, filename: str, content_type: str):
    import uuid

    from django.core.files.base import ContentFile

    from apps.files.models import File

    cf = ContentFile(content, name=filename)
    file_obj = File.objects.create(
        original_file_name=filename,
        file_name=f"{uuid.uuid4()}_{filename}",
        file_type=content_type,
    )
    file_obj.file.save(file_obj.file_name, cf, save=True)
    file_obj.upload_finished_at = timezone.now()
    file_obj.save(update_fields=["upload_finished_at"])
    return file_obj

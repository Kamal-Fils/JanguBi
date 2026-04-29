"""
Tests for apps/emails/services.py — HackSoft Styleguide.
Pattern AAA (Arrange / Act / Assert) on every test.
All SMTP calls are patched — no real email is ever sent.
"""

from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ApplicationError
from apps.emails.models import Email
from apps.emails.services import email_failed, email_send, email_send_all, send_multi_format_email

from .factories import EmailFactory, FailedEmailFactory, SendingEmailFactory, SentEmailFactory


# ---------------------------------------------------------------------------
# email_failed
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_email_failed_marks_email_as_failed():
    # Arrange
    email = SendingEmailFactory()

    # Act
    result = email_failed(email)

    # Assert
    assert result.status == Email.Status.FAILED
    email.refresh_from_db()
    assert email.status == Email.Status.FAILED


@pytest.mark.django_db
def test_email_failed_returns_updated_email_instance():
    # Arrange
    email = SendingEmailFactory()

    # Act
    result = email_failed(email)

    # Assert — service returns the same Email object (same pk)
    assert result.pk == email.pk


@pytest.mark.django_db
def test_email_failed_raises_when_status_is_ready():
    # Arrange
    email = EmailFactory(status=Email.Status.READY)

    # Act & Assert
    with pytest.raises(ApplicationError) as exc_info:
        email_failed(email)

    assert "READY" in str(exc_info.value)


@pytest.mark.django_db
def test_email_failed_raises_when_status_is_sent():
    # Arrange
    email = SentEmailFactory()

    # Act & Assert
    with pytest.raises(ApplicationError) as exc_info:
        email_failed(email)

    assert "SENT" in str(exc_info.value)


@pytest.mark.django_db
def test_email_failed_raises_when_status_is_already_failed():
    # Arrange
    email = FailedEmailFactory()

    # Act & Assert
    with pytest.raises(ApplicationError) as exc_info:
        email_failed(email)

    assert "FAILED" in str(exc_info.value)


@pytest.mark.django_db
def test_email_failed_does_not_persist_when_exception_is_raised():
    """@transaction.atomic must roll back — DB row is unchanged on error."""
    # Arrange
    email = EmailFactory(status=Email.Status.READY)

    # Act & Assert
    with pytest.raises(ApplicationError):
        email_failed(email)

    email.refresh_from_db()
    assert email.status == Email.Status.READY


# ---------------------------------------------------------------------------
# email_send
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_email_send_success_marks_email_as_sent():
    # Arrange
    email = SendingEmailFactory()

    # Act
    with patch("apps.emails.services.EmailMultiAlternatives") as mock_msg_class:
        mock_msg_class.return_value = MagicMock()
        result = email_send(email)

    # Assert
    assert result.status == Email.Status.SENT
    assert result.sent_at is not None
    email.refresh_from_db()
    assert email.status == Email.Status.SENT


@pytest.mark.django_db
def test_email_send_persists_sent_at_timestamp():
    # Arrange
    email = SendingEmailFactory()

    # Act
    with patch("apps.emails.services.EmailMultiAlternatives") as mock_msg_class:
        mock_msg_class.return_value = MagicMock()
        result = email_send(email)

    # Assert — sent_at is populated after a successful send
    assert result.sent_at is not None
    email.refresh_from_db()
    assert email.sent_at is not None


@pytest.mark.django_db
def test_email_send_calls_smtp_with_correct_fields():
    # Arrange
    email = SendingEmailFactory(
        to="test@example.com",
        subject="Hello",
        html="<p>Hi</p>",
        plain_text="Hi",
    )

    # Act
    with patch("apps.emails.services.EmailMultiAlternatives") as mock_msg_class:
        mock_msg = MagicMock()
        mock_msg_class.return_value = mock_msg
        email_send(email)

    # Assert — constructor called with (subject, plain_text, from_email, [to])
    args, _ = mock_msg_class.call_args
    assert args[0] == "Hello"
    assert args[1] == "Hi"
    assert args[3] == ["test@example.com"]
    mock_msg.attach_alternative.assert_called_once_with("<p>Hi</p>", "text/html")
    mock_msg.send.assert_called_once()


@pytest.mark.django_db
def test_email_send_raises_when_status_is_ready():
    # Arrange
    email = EmailFactory(status=Email.Status.READY)

    # Act & Assert
    with pytest.raises(ApplicationError) as exc_info:
        email_send(email)

    assert "READY" in str(exc_info.value)


@pytest.mark.django_db
def test_email_send_raises_when_status_is_sent():
    # Arrange
    email = SentEmailFactory()

    # Act & Assert
    with pytest.raises(ApplicationError) as exc_info:
        email_send(email)

    assert "SENT" in str(exc_info.value)


@pytest.mark.django_db
def test_email_send_raises_when_status_is_failed():
    # Arrange
    email = FailedEmailFactory()

    # Act & Assert
    with pytest.raises(ApplicationError) as exc_info:
        email_send(email)

    assert "FAILED" in str(exc_info.value)


@pytest.mark.django_db
def test_email_send_raises_when_failure_trigger_fires(settings):
    # Arrange — force the random failure path by setting rate to 100 %
    settings.EMAIL_SENDING_FAILURE_TRIGGER = True
    settings.EMAIL_SENDING_FAILURE_RATE = 1.0
    email = SendingEmailFactory()

    # Act & Assert
    with pytest.raises(ApplicationError) as exc_info:
        email_send(email)

    assert "failure triggered" in str(exc_info.value).lower()


@pytest.mark.django_db
def test_email_send_does_not_raise_when_failure_trigger_disabled(settings):
    # Arrange
    settings.EMAIL_SENDING_FAILURE_TRIGGER = False
    email = SendingEmailFactory()

    # Act
    with patch("apps.emails.services.EmailMultiAlternatives") as mock_msg_class:
        mock_msg_class.return_value = MagicMock()
        result = email_send(email)

    # Assert
    assert result.status == Email.Status.SENT


@pytest.mark.django_db
def test_email_send_does_not_raise_when_failure_rate_is_zero(settings):
    # Arrange — trigger active but rate is 0 % (dice always exceeds 0.0, never fires)
    settings.EMAIL_SENDING_FAILURE_TRIGGER = True
    settings.EMAIL_SENDING_FAILURE_RATE = 0.0
    email = SendingEmailFactory()

    # Act
    with patch("apps.emails.services.EmailMultiAlternatives") as mock_msg_class:
        mock_msg_class.return_value = MagicMock()
        result = email_send(email)

    # Assert — email sent normally because random.uniform(0,1) > 0.0 always
    assert result.status == Email.Status.SENT


@pytest.mark.django_db
def test_email_send_does_not_persist_changes_when_trigger_fires(settings):
    """@transaction.atomic must roll back sent_at when the failure trigger fires."""
    # Arrange
    settings.EMAIL_SENDING_FAILURE_TRIGGER = True
    settings.EMAIL_SENDING_FAILURE_RATE = 1.0
    email = SendingEmailFactory()

    # Act & Assert
    with pytest.raises(ApplicationError):
        email_send(email)

    email.refresh_from_db()
    assert email.sent_at is None
    assert email.status == Email.Status.SENDING


# ---------------------------------------------------------------------------
# email_send_all
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_email_send_all_sets_status_to_sending_and_enqueues_tasks():
    # Arrange — two READY emails
    email1 = EmailFactory(status=Email.Status.READY)
    email2 = EmailFactory(status=Email.Status.READY)
    queryset = Email.objects.filter(id__in=[email1.id, email2.id])

    # Act — patch the Celery task so nothing is actually enqueued
    with patch("apps.emails.services.email_send_task") as mock_task:
        email_send_all(queryset)

    # Assert — both rows transitioned to SENDING in the DB
    email1.refresh_from_db()
    email2.refresh_from_db()
    assert email1.status == Email.Status.SENDING
    assert email2.status == Email.Status.SENDING

    # Assert — delay called once per email with the correct id
    assert mock_task.delay.call_count == 2
    called_ids = {c.args[0] for c in mock_task.delay.call_args_list}
    assert called_ids == {email1.id, email2.id}


@pytest.mark.django_db
def test_email_send_all_with_empty_queryset_does_not_enqueue():
    # Arrange
    queryset = Email.objects.none()

    # Act
    with patch("apps.emails.services.email_send_task") as mock_task:
        email_send_all(queryset)

    # Assert
    mock_task.delay.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_email_send_all_enqueues_each_email_individually():
    """Each email must produce its own separate task — not a single batch call."""
    # Arrange
    emails = [EmailFactory(status=Email.Status.READY) for _ in range(3)]
    queryset = Email.objects.filter(id__in=[e.id for e in emails])

    # Act
    with patch("apps.emails.services.email_send_task") as mock_task:
        email_send_all(queryset)

    # Assert — one delay call per email
    assert mock_task.delay.call_count == 3


@pytest.mark.django_db(transaction=True)
def test_email_send_all_closure_captures_correct_ids():
    """
    Guard against a classic Python closure late-binding bug.
    Each task must be called with a distinct email id, not the same final id.
    """
    # Arrange
    email1 = EmailFactory(status=Email.Status.READY)
    email2 = EmailFactory(status=Email.Status.READY)
    expected_ids = {email1.id, email2.id}
    queryset = Email.objects.filter(id__in=expected_ids)

    # Act
    with patch("apps.emails.services.email_send_task") as mock_task:
        email_send_all(queryset)

    # Assert — each delay call received a unique, correct email id
    actual_ids = {c.args[0] for c in mock_task.delay.call_args_list}
    assert actual_ids == expected_ids


# ---------------------------------------------------------------------------
# send_multi_format_email
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_send_multi_format_email_creates_email_record_and_sends():
    # Arrange
    template_ctxt = {"verification_link": "https://example.com/verify/abc123"}
    target_email = "user@example.com"

    # Act — patch template rendering and SMTP
    with (
        patch("apps.emails.services.render_to_string") as mock_render,
        patch("apps.emails.services.EmailMultiAlternatives") as mock_msg_class,
    ):
        mock_render.side_effect = [
            "Verify your email",  # subject template
            "<p>Click here</p>",  # html template
            "Click here",         # plain_text template
        ]
        mock_msg_class.return_value = MagicMock()

        send_multi_format_email(
            template_prefix="email_verification",
            template_ctxt=template_ctxt,
            target_email=target_email,
        )

    # Assert — Email record persisted with correct fields and SENT status
    assert Email.objects.filter(to=target_email).exists()
    email = Email.objects.get(to=target_email)
    assert email.subject == "Verify your email"
    assert email.html == "<p>Click here</p>"
    assert email.plain_text == "Click here"
    assert email.status == Email.Status.SENT
    assert email.sent_at is not None


@pytest.mark.django_db
def test_send_multi_format_email_uses_correct_template_paths():
    # Arrange & Act
    with (
        patch("apps.emails.services.render_to_string") as mock_render,
        patch("apps.emails.services.EmailMultiAlternatives") as mock_msg_class,
    ):
        mock_render.side_effect = ["Subject", "<p>HTML</p>", "Plain"]
        mock_msg_class.return_value = MagicMock()

        send_multi_format_email(
            template_prefix="password_reset_email",
            template_ctxt={},
            target_email="u@example.com",
            path_prefix="auth",
        )

    # Assert — render_to_string called with the expected template paths in order
    template_names = [c.args[0] for c in mock_render.call_args_list]
    assert template_names[0] == "auth/password_reset_email_subject.txt"
    assert template_names[1] == "auth/password_reset_email.html"
    assert template_names[2] == "auth/password_reset_email.txt"


@pytest.mark.django_db
def test_send_multi_format_email_strips_whitespace_from_subject():
    # Arrange — subject template returns value with surrounding whitespace
    with (
        patch("apps.emails.services.render_to_string") as mock_render,
        patch("apps.emails.services.EmailMultiAlternatives") as mock_msg_class,
    ):
        mock_render.side_effect = ["  Hello World  \n", "<p>body</p>", "body"]
        mock_msg_class.return_value = MagicMock()

        send_multi_format_email(
            template_prefix="welcome_email",
            template_ctxt={},
            target_email="strip@example.com",
        )

    # Assert — subject persisted without leading/trailing whitespace
    email = Email.objects.get(to="strip@example.com")
    assert email.subject == "Hello World"


@pytest.mark.django_db
def test_send_multi_format_email_uses_custom_path_prefix():
    # Arrange — path_prefix other than the default "auth"
    with (
        patch("apps.emails.services.render_to_string") as mock_render,
        patch("apps.emails.services.EmailMultiAlternatives") as mock_msg_class,
    ):
        mock_render.side_effect = ["Subject", "<p>Body</p>", "Body"]
        mock_msg_class.return_value = MagicMock()

        send_multi_format_email(
            template_prefix="parish_invite",
            template_ctxt={},
            target_email="member@example.com",
            path_prefix="documents",
        )

    # Assert — all three render calls use the custom path_prefix
    template_names = [c.args[0] for c in mock_render.call_args_list]
    assert template_names[0] == "documents/parish_invite_subject.txt"
    assert template_names[1] == "documents/parish_invite.html"
    assert template_names[2] == "documents/parish_invite.txt"


@pytest.mark.django_db
def test_send_multi_format_email_passes_context_to_all_templates():
    # Arrange
    ctx = {"name": "Marie", "link": "https://example.com/token"}

    with (
        patch("apps.emails.services.render_to_string") as mock_render,
        patch("apps.emails.services.EmailMultiAlternatives") as mock_msg_class,
    ):
        mock_render.side_effect = ["Subject", "<p>Hi Marie</p>", "Hi Marie"]
        mock_msg_class.return_value = MagicMock()

        send_multi_format_email(
            template_prefix="welcome",
            template_ctxt=ctx,
            target_email="marie@example.com",
        )

    # Assert — every render_to_string call received the same context dict
    for render_call in mock_render.call_args_list:
        # render_to_string(template_name, context) — context is the second positional arg
        passed_ctx = render_call.args[1] if len(render_call.args) > 1 else render_call.kwargs.get("context")
        assert passed_ctx == ctx


@pytest.mark.django_db
def test_send_multi_format_email_does_not_persist_email_when_smtp_fails():
    """@transaction.atomic must roll back the Email record if SMTP raises."""
    # Arrange
    with (
        patch("apps.emails.services.render_to_string") as mock_render,
        patch("apps.emails.services.EmailMultiAlternatives") as mock_msg_class,
    ):
        mock_render.side_effect = ["Subject", "<p>Body</p>", "Body"]
        mock_msg = MagicMock()
        mock_msg.send.side_effect = Exception("SMTP connection refused")
        mock_msg_class.return_value = mock_msg

        with pytest.raises(Exception, match="SMTP connection refused"):
            send_multi_format_email(
                template_prefix="welcome",
                template_ctxt={},
                target_email="rollback@example.com",
            )

    # Assert — no Email record was committed to the DB
    assert not Email.objects.filter(to="rollback@example.com").exists()

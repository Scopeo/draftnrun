from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from ada_backend.database.models import CallType, RunStatus
from ada_backend.services.alerting.alert_service import _build_alert_html

EMAIL_SERVICE_MODULE = "ada_backend.services.alerting.email_service"
ALERT_SERVICE_MODULE = "ada_backend.services.alerting.alert_service"


def _make_fake_run(trigger=CallType.WEBHOOK, project_id=None):
    run = MagicMock()
    run.id = uuid4()
    run.project_id = project_id or uuid4()
    run.trigger = trigger
    run.status = RunStatus.FAILED
    run.error = {"message": "timeout", "type": "TimeoutError"}
    run.finished_at = datetime.now(timezone.utc)
    return run


class TestBuildAlertHtml:
    def test_escapes_html_in_user_controlled_fields(self):
        xss_payload = '<script>alert("xss")</script>'
        result = _build_alert_html(
            project_name=xss_payload,
            run_id=uuid4(),
            trigger=xss_payload,
            error={"message": xss_payload, "type": xss_payload},
            finished_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        assert "<script>" not in result
        assert "&lt;script&gt;" in result


class TestSendEmail:
    @patch(f"{EMAIL_SERVICE_MODULE}.settings")
    @patch(f"{EMAIL_SERVICE_MODULE}.httpx")
    def test_sends_email_via_resend(self, mock_httpx, mock_settings):
        mock_settings.RESEND_API_KEY = "test-key"
        mock_settings.RESEND_FROM_EMAIL = "alerts@test.com"

        mock_client = MagicMock()
        mock_httpx.Client.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_httpx.Client.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value.raise_for_status = MagicMock()

        from ada_backend.services.alerting.email_service import send_email

        send_email(to=["user@test.com"], subject="Test", html="<p>Test</p>")

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert call_kwargs.kwargs["json"]["to"] == ["user@test.com"]
        assert call_kwargs.kwargs["json"]["subject"] == "Test"

    @patch(f"{EMAIL_SERVICE_MODULE}.settings")
    def test_noop_when_api_key_missing(self, mock_settings):
        mock_settings.RESEND_API_KEY = None
        mock_settings.RESEND_FROM_EMAIL = "alerts@test.com"

        from ada_backend.services.alerting.email_service import send_email

        send_email(to=["user@test.com"], subject="Test", html="<p>Test</p>")

    @patch(f"{EMAIL_SERVICE_MODULE}.settings")
    def test_noop_when_from_email_missing(self, mock_settings):
        mock_settings.RESEND_API_KEY = "test-key"
        mock_settings.RESEND_FROM_EMAIL = None

        from ada_backend.services.alerting.email_service import send_email

        send_email(to=["user@test.com"], subject="Test", html="<p>Test</p>")

    @patch(f"{EMAIL_SERVICE_MODULE}.settings")
    @patch(f"{EMAIL_SERVICE_MODULE}.httpx")
    def test_does_not_raise_on_http_error(self, mock_httpx, mock_settings):
        import httpx as real_httpx

        mock_settings.RESEND_API_KEY = "test-key"
        mock_settings.RESEND_FROM_EMAIL = "alerts@test.com"

        mock_client = MagicMock()
        mock_httpx.Client.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_httpx.Client.return_value.__exit__ = MagicMock(return_value=False)
        mock_httpx.HTTPStatusError = real_httpx.HTTPStatusError
        mock_client.post.return_value.raise_for_status.side_effect = real_httpx.HTTPStatusError(
            "error", request=MagicMock(), response=MagicMock()
        )

        from ada_backend.services.alerting.email_service import send_email

        send_email(to=["user@test.com"], subject="Test", html="<p>Test</p>")


class TestSendRunFailureAlert:
    @patch(f"{ALERT_SERVICE_MODULE}.send_email")
    @patch(f"{ALERT_SERVICE_MODULE}.get_db_session")
    @patch(f"{ALERT_SERVICE_MODULE}.settings")
    def test_sends_alert_for_webhook_trigger(self, mock_settings, mock_get_db, mock_send_email):
        mock_settings.RESEND_API_KEY = "test-key"
        mock_settings.RESEND_FROM_EMAIL = "alerts@test.com"

        project_id = uuid4()
        session = MagicMock()
        mock_get_db.return_value.__enter__ = MagicMock(return_value=session)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        mock_recipient = MagicMock()
        mock_recipient.email = "dev@test.com"
        session.query.return_value.filter.return_value.all.return_value = [mock_recipient]

        mock_project = MagicMock()
        mock_project.name = "My Agent"

        with patch(f"{ALERT_SERVICE_MODULE}.get_project", return_value=mock_project):
            from ada_backend.services.alerting.alert_service import _send_run_failure_alert

            _send_run_failure_alert(
                run_id=uuid4(),
                project_id=project_id,
                trigger=CallType.WEBHOOK,
                error={"message": "timeout", "type": "TimeoutError"},
                finished_at=datetime.now(timezone.utc),
            )

        mock_send_email.assert_called_once()
        call_kwargs = mock_send_email.call_args
        assert call_kwargs.kwargs["to"] == ["dev@test.com"]
        assert "My Agent" in call_kwargs.kwargs["subject"]

    @patch(f"{ALERT_SERVICE_MODULE}.send_email")
    @patch(f"{ALERT_SERVICE_MODULE}.get_db_session")
    @patch(f"{ALERT_SERVICE_MODULE}.settings")
    def test_sends_alert_for_cron_trigger(self, mock_settings, mock_get_db, mock_send_email):
        mock_settings.RESEND_API_KEY = "test-key"
        mock_settings.RESEND_FROM_EMAIL = "alerts@test.com"

        session = MagicMock()
        mock_get_db.return_value.__enter__ = MagicMock(return_value=session)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        mock_recipient = MagicMock()
        mock_recipient.email = "ops@test.com"
        session.query.return_value.filter.return_value.all.return_value = [mock_recipient]

        mock_project = MagicMock()
        mock_project.name = "Cron Agent"

        with patch(f"{ALERT_SERVICE_MODULE}.get_project", return_value=mock_project):
            from ada_backend.services.alerting.alert_service import _send_run_failure_alert

            _send_run_failure_alert(
                run_id=uuid4(),
                project_id=uuid4(),
                trigger=CallType.CRON,
                error={"message": "crash", "type": "RuntimeError"},
                finished_at=datetime.now(timezone.utc),
            )

        mock_send_email.assert_called_once()

    @patch(f"{ALERT_SERVICE_MODULE}.send_email")
    @patch(f"{ALERT_SERVICE_MODULE}.settings")
    def test_skips_api_trigger(self, mock_settings, mock_send_email):
        mock_settings.RESEND_API_KEY = "test-key"
        mock_settings.RESEND_FROM_EMAIL = "alerts@test.com"

        from ada_backend.services.alerting.alert_service import _send_run_failure_alert

        _send_run_failure_alert(
            run_id=uuid4(),
            project_id=uuid4(),
            trigger=CallType.API,
            error={"message": "err", "type": "Error"},
            finished_at=datetime.now(timezone.utc),
        )

        mock_send_email.assert_not_called()

    @patch(f"{ALERT_SERVICE_MODULE}.send_email")
    @patch(f"{ALERT_SERVICE_MODULE}.settings")
    def test_skips_sandbox_trigger(self, mock_settings, mock_send_email):
        mock_settings.RESEND_API_KEY = "test-key"
        mock_settings.RESEND_FROM_EMAIL = "alerts@test.com"

        from ada_backend.services.alerting.alert_service import _send_run_failure_alert

        _send_run_failure_alert(
            run_id=uuid4(),
            project_id=uuid4(),
            trigger=CallType.SANDBOX,
            error={"message": "err", "type": "Error"},
            finished_at=datetime.now(timezone.utc),
        )

        mock_send_email.assert_not_called()

    @patch(f"{ALERT_SERVICE_MODULE}.send_email")
    @patch(f"{ALERT_SERVICE_MODULE}.get_db_session")
    @patch(f"{ALERT_SERVICE_MODULE}.settings")
    def test_skips_when_no_recipients(self, mock_settings, mock_get_db, mock_send_email):
        mock_settings.RESEND_API_KEY = "test-key"
        mock_settings.RESEND_FROM_EMAIL = "alerts@test.com"

        session = MagicMock()
        mock_get_db.return_value.__enter__ = MagicMock(return_value=session)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
        session.query.return_value.filter.return_value.all.return_value = []

        from ada_backend.services.alerting.alert_service import _send_run_failure_alert

        _send_run_failure_alert(
            run_id=uuid4(),
            project_id=uuid4(),
            trigger=CallType.WEBHOOK,
            error={"message": "err", "type": "Error"},
            finished_at=datetime.now(timezone.utc),
        )

        mock_send_email.assert_not_called()

    @patch(f"{ALERT_SERVICE_MODULE}.settings")
    def test_skips_when_resend_not_configured(self, mock_settings):
        mock_settings.RESEND_API_KEY = None
        mock_settings.RESEND_FROM_EMAIL = None

        from ada_backend.services.alerting.alert_service import _send_run_failure_alert

        _send_run_failure_alert(
            run_id=uuid4(),
            project_id=uuid4(),
            trigger=CallType.WEBHOOK,
            error={"message": "err", "type": "Error"},
            finished_at=datetime.now(timezone.utc),
        )

    @patch(f"{ALERT_SERVICE_MODULE}.send_email")
    @patch(f"{ALERT_SERVICE_MODULE}.get_db_session")
    @patch(f"{ALERT_SERVICE_MODULE}.settings")
    def test_does_not_raise_on_exception(self, mock_settings, mock_get_db, mock_send_email):
        mock_settings.RESEND_API_KEY = "test-key"
        mock_settings.RESEND_FROM_EMAIL = "alerts@test.com"

        mock_get_db.return_value.__enter__ = MagicMock(side_effect=Exception("db error"))

        from ada_backend.services.alerting.alert_service import _send_run_failure_alert

        _send_run_failure_alert(
            run_id=uuid4(),
            project_id=uuid4(),
            trigger=CallType.WEBHOOK,
            error={"message": "err", "type": "Error"},
            finished_at=datetime.now(timezone.utc),
        )

        mock_send_email.assert_not_called()


class TestMaybeSendRunFailureAlert:
    @patch(f"{ALERT_SERVICE_MODULE}.threading")
    def test_spawns_thread_for_webhook_trigger(self, mock_threading):
        run = _make_fake_run(trigger=CallType.WEBHOOK)

        from ada_backend.services.alerting.alert_service import maybe_send_run_failure_alert

        maybe_send_run_failure_alert(run, run.project_id, error=run.error)

        mock_threading.Thread.assert_called_once()
        mock_threading.Thread.return_value.start.assert_called_once()

    @patch(f"{ALERT_SERVICE_MODULE}.threading")
    def test_spawns_thread_for_cron_trigger(self, mock_threading):
        run = _make_fake_run(trigger=CallType.CRON)

        from ada_backend.services.alerting.alert_service import maybe_send_run_failure_alert

        maybe_send_run_failure_alert(run, run.project_id, error=run.error)

        mock_threading.Thread.assert_called_once()

    @patch(f"{ALERT_SERVICE_MODULE}.threading")
    def test_skips_thread_for_api_trigger(self, mock_threading):
        run = _make_fake_run(trigger=CallType.API)

        from ada_backend.services.alerting.alert_service import maybe_send_run_failure_alert

        maybe_send_run_failure_alert(run, run.project_id, error=run.error)

        mock_threading.Thread.assert_not_called()

    @patch(f"{ALERT_SERVICE_MODULE}.threading")
    def test_skips_thread_for_qa_trigger(self, mock_threading):
        run = _make_fake_run(trigger=CallType.QA)

        from ada_backend.services.alerting.alert_service import maybe_send_run_failure_alert

        maybe_send_run_failure_alert(run, run.project_id, error=run.error)

        mock_threading.Thread.assert_not_called()

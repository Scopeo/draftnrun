import logging
import threading
from datetime import datetime, timezone
from uuid import UUID

from ada_backend.database.models import CallType, ProjectAlertEmail, Run
from ada_backend.database.setup_db import get_db_session
from ada_backend.repositories.project_repository import get_project
from ada_backend.services.alerting.email_service import send_email
from settings import settings

LOGGER = logging.getLogger(__name__)

_ALERT_TRIGGERS = frozenset({CallType.WEBHOOK, CallType.CRON})


def _build_alert_html(
    project_name: str,
    run_id: UUID,
    trigger: str,
    error: dict | None,
    finished_at: datetime | None,
) -> str:
    error_message = "Unknown error"
    error_type = "Unknown"
    if error:
        error_message = error.get("message", "Unknown error")
        error_type = error.get("type", "Unknown")

    timestamp = (finished_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M:%S UTC")

    return f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #dc2626;">Run Failed</h2>
        <table style="width: 100%; border-collapse: collapse;">
            <tr>
                <td style="padding: 8px; font-weight: bold; color: #374151;">Project</td>
                <td style="padding: 8px; color: #111827;">{project_name}</td>
            </tr>
            <tr style="background: #f9fafb;">
                <td style="padding: 8px; font-weight: bold; color: #374151;">Run ID</td>
                <td style="padding: 8px; color: #111827; font-family: monospace;">{run_id}</td>
            </tr>
            <tr>
                <td style="padding: 8px; font-weight: bold; color: #374151;">Trigger</td>
                <td style="padding: 8px; color: #111827;">{trigger}</td>
            </tr>
            <tr style="background: #f9fafb;">
                <td style="padding: 8px; font-weight: bold; color: #374151;">Error Type</td>
                <td style="padding: 8px; color: #111827;">{error_type}</td>
            </tr>
            <tr>
                <td style="padding: 8px; font-weight: bold; color: #374151;">Error</td>
                <td style="padding: 8px; color: #dc2626;">{error_message}</td>
            </tr>
            <tr style="background: #f9fafb;">
                <td style="padding: 8px; font-weight: bold; color: #374151;">Time</td>
                <td style="padding: 8px; color: #111827;">{timestamp}</td>
            </tr>
        </table>
    </div>
    """


def _send_run_failure_alert(
    run_id: UUID,
    project_id: UUID,
    trigger: CallType,
    error: dict | None,
    finished_at: datetime | None,
) -> None:
    try:
        if not settings.RESEND_API_KEY or not settings.RESEND_FROM_EMAIL:
            LOGGER.warning("Resend not configured (RESEND_API_KEY or RESEND_FROM_EMAIL missing), skipping alert")
            return

        trigger_value = trigger if isinstance(trigger, str) else trigger.value
        if trigger_value not in {t.value for t in _ALERT_TRIGGERS}:
            return

        with get_db_session() as session:
            recipients = (
                session.query(ProjectAlertEmail.email).filter(ProjectAlertEmail.project_id == project_id).all()
            )
            if not recipients:
                return
            emails = [r.email for r in recipients]

            project = get_project(session, project_id=project_id)
            project_name = project.name if project else str(project_id)

        subject = f"[Draft'n Run] Run failed — {project_name}"
        html = _build_alert_html(
            project_name=project_name,
            run_id=run_id,
            trigger=trigger_value,
            error=error,
            finished_at=finished_at,
        )
        send_email(to=emails, subject=subject, html=html)
    except Exception:
        LOGGER.exception("Failed to send run failure alert for run_id=%s", run_id)


def maybe_send_run_failure_alert(
    run: Run,
    project_id: UUID,
    error: dict | None = None,
    finished_at: datetime | None = None,
) -> None:
    trigger = run.trigger if isinstance(run.trigger, CallType) else CallType(str(run.trigger))
    if trigger not in _ALERT_TRIGGERS:
        return

    thread = threading.Thread(
        target=_send_run_failure_alert,
        args=(run.id, project_id, trigger, error, finished_at),
        daemon=True,
    )
    thread.start()

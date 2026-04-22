import asyncio
import logging
import signal
import sys
from typing import Optional

import sentry_sdk
from sentry_sdk.crons import capture_checkin
from sentry_sdk.crons.consts import MonitorStatus

from ada_backend.scheduler.service import (
    initialize_scheduler_trace_manager,
    start_scheduler,
    stop_scheduler,
)
from engine.trace.trace_context import set_trace_manager
from logger import setup_logging
from settings import settings
from shared.log_redaction import scrub_sentry_event

LOGGER = logging.getLogger(__name__)

SHUTDOWN_EVENT: Optional[asyncio.Event] = None

SENTRY_MONITOR_SLUG = "run-scheduler"


def signal_handler(signum, frame):
    """
    Handle shutdown signals from the OS gracefully.

    This function is called by the OS when:
    - SIGTERM is received (e.g., from systemd: systemctl stop)
    - SIGINT is received (e.g., from user: Ctrl+C)

    Args:
        signum: Signal number (e.g., 15 for SIGTERM, 2 for SIGINT)
        frame: Current stack frame (not used, but required by signal handler signature)
    """
    signal_name = signal.Signals(signum).name
    LOGGER.info(f"Received {signal_name} signal. Initiating graceful shutdown...")

    if SHUTDOWN_EVENT:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.call_soon_threadsafe(SHUTDOWN_EVENT.set)
            else:
                # Loop exists but not running - this shouldn't happen in a normal flow
                error_msg = "SHUTDOWN_EVENT was initialized outside of a running loop"
                LOGGER.error(error_msg)
        except RuntimeError as e:
            # No event loop exists - this shouldn't happen if SHUTDOWN_EVENT exists
            error_msg = "SHUTDOWN_EVENT was initialized outside of a loop"
            LOGGER.error(f"{error_msg}: {e}")


async def run_scheduler():
    global SHUTDOWN_EVENT

    setup_logging(process_name="apscheduler")

    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.SENTRY_ENVIRONMENT,
            send_default_pii=settings.SENTRY_SEND_PII,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            enable_logs=True,
            profile_session_sample_rate=settings.SENTRY_PROFILE_SESSION_SAMPLE_RATE,
            profile_lifecycle="trace",
            before_send=lambda event, hint: scrub_sentry_event(event),
            before_send_log=lambda log, hint: scrub_sentry_event(log),
            before_send_transaction=lambda event, hint: scrub_sentry_event(event),
        )

    # Initialize the shared TraceManager singleton early
    # This ensures we only create one TraceManager instance for all scheduler jobs
    trace_manager = initialize_scheduler_trace_manager()
    set_trace_manager(tm=trace_manager)

    SHUTDOWN_EVENT = asyncio.Event()

    LOGGER.info("Starting APScheduler as standalone process")

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    _scheduler_failed = False
    check_in_id = capture_checkin(
        monitor_slug=SENTRY_MONITOR_SLUG,
        status=MonitorStatus.IN_PROGRESS,
        monitor_config={
            # Continuous deploys on weekdays: expect a restart at least every 12h.
            # If no check-in arrives within that window, Sentry flags the monitor as missed.
            "schedule": {"type": "interval", "value": 12, "unit": "hour"},
            "timezone": "UTC",
            "checkin_margin": 60,  # minutes grace period before flagging as missed
            "max_runtime": 1440,  # minutes — process runs all day
            "failure_issue_threshold": 1,
            "recovery_threshold": 1,
        },
    )

    try:
        start_scheduler()
        LOGGER.info("APScheduler started successfully. Waiting for shutdown signal...")
        await SHUTDOWN_EVENT.wait()
        LOGGER.info("Shutdown signal received")

    except Exception as e:
        _scheduler_failed = True
        error_msg = f"Failed to start scheduler: {e}"
        LOGGER.error(error_msg, exc_info=True)
        raise
    finally:
        LOGGER.info("Shutting down APScheduler...")
        try:
            stop_scheduler()  # This waits for running jobs to complete (wait=True)
            LOGGER.info("APScheduler shut down successfully")
        except Exception as e:
            _scheduler_failed = True
            error_msg = f"Error during scheduler shutdown: {e}"
            LOGGER.error(error_msg, exc_info=True)
            raise
        finally:
            capture_checkin(
                monitor_slug=SENTRY_MONITOR_SLUG,
                check_in_id=check_in_id,
                status=MonitorStatus.ERROR if _scheduler_failed else MonitorStatus.OK,
            )


def main():
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        loop.run_until_complete(run_scheduler())

    except Exception as e:
        error_msg = f"Fatal error in scheduler: {e}"
        LOGGER.error(error_msg, exc_info=True)
        # Exit with code 1 to indicate failure to systemd, CI/CD, and monitoring tools
        sys.exit(1)
    finally:
        try:
            loop = asyncio.get_event_loop()
            if loop and not loop.is_closed():
                loop.close()
        except RuntimeError:
            pass


if __name__ == "__main__":
    main()

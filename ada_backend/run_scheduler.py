import asyncio
import signal
import sys
import logging
from typing import Optional

from logger import setup_logging
from engine.trace.trace_context import set_trace_manager
from engine.trace.trace_manager import TraceManager
from ada_backend.scheduler.service import start_scheduler, stop_scheduler

LOGGER = logging.getLogger(__name__)

SHUTDOWN_EVENT: Optional[asyncio.Event] = None


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
                print(f"❌ {error_msg}", file=sys.stderr)
        except RuntimeError as e:
            # No event loop exists - this shouldn't happen if SHUTDOWN_EVENT exists
            error_msg = "SHUTDOWN_EVENT was initialized outside of a loop"
            LOGGER.error(f"{error_msg}: {e}")
            print(f"❌ {error_msg}", file=sys.stderr)


async def run_scheduler():
    global SHUTDOWN_EVENT

    setup_logging(process_name="apscheduler")

    set_trace_manager(tm=TraceManager(project_name="ada-backend-scheduler"))

    SHUTDOWN_EVENT = asyncio.Event()

    LOGGER.info("Starting APScheduler as standalone process")

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        start_scheduler()
        LOGGER.info("APScheduler started successfully. Waiting for shutdown signal...")
        await SHUTDOWN_EVENT.wait()
        LOGGER.info("Shutdown signal received")

    except Exception as e:
        error_msg = f"❌ Failed to start scheduler: {e}"
        LOGGER.error(error_msg, exc_info=True)
        print(error_msg, file=sys.stderr)
        raise
    finally:
        LOGGER.info("Shutting down APScheduler...")
        try:
            stop_scheduler()  # This waits for running jobs to complete (wait=True)
            LOGGER.info("APScheduler shut down successfully")
        except Exception as e:
            error_msg = f"❌ Error during scheduler shutdown: {e}"
            LOGGER.error(error_msg, exc_info=True)
            print(error_msg, file=sys.stderr)
            raise


def main():
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        loop.run_until_complete(run_scheduler())

    except Exception as e:
        error_msg = f"❌ Fatal error in scheduler: {e}"
        LOGGER.error(error_msg, exc_info=True)
        print(error_msg, file=sys.stderr)
        print(f"   Error type: {type(e).__name__}", file=sys.stderr)
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

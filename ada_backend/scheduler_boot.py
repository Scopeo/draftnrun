"""
This module is responsible for starting and stopping the scheduler.
"""

import logging
from contextlib import asynccontextmanager

from ada_backend.scheduler.service import start_scheduler, stop_scheduler

LOGGER = logging.getLogger(__name__)


def initialize_scheduler():
    """
    Initialize the scheduler during application startup.
    This function is called from the FastAPI startup event.
    """
    try:
        LOGGER.info("Initializing cron scheduler...")
        start_scheduler()
        LOGGER.info("Cron scheduler initialized successfully")
    except Exception as e:
        LOGGER.error(f"Failed to initialize scheduler: {e}")
        # Don't raise the exception to prevent app startup failure
        # The scheduler can be started manually later if needed


def shutdown_scheduler():
    """
    Shutdown the scheduler during application shutdown.
    This function is called from the FastAPI shutdown event.
    """
    try:
        LOGGER.info("Shutting down cron scheduler...")
        stop_scheduler()
        LOGGER.info("Cron scheduler shut down successfully")
    except Exception as e:
        LOGGER.error(f"Error shutting down scheduler: {e}")


@asynccontextmanager
async def scheduler_lifespan(app):
    """
    Context manager for scheduler lifecycle management.
    This can be used with FastAPI's lifespan parameter.

    Usage:
        app = FastAPI(lifespan=scheduler_lifespan)
    """
    # Startup
    LOGGER.info("Starting application with cron scheduler...")
    try:
        initialize_scheduler()
        yield
    finally:
        # Shutdown
        LOGGER.info("Shutting down application and cron scheduler...")
        shutdown_scheduler()

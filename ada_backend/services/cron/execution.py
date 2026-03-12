"""Shared cron execution logic used by both the scheduler and manual trigger."""

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from ada_backend.database.models import CronEntrypoint, CronStatus
from ada_backend.database.setup_db import get_db_session
from ada_backend.repositories.cron_repository import update_cron_run
from ada_backend.services.cron.core import AsyncCronJobResult
from ada_backend.services.cron.registry import CRON_REGISTRY

LOGGER = logging.getLogger(__name__)


async def run_cron_spec(
    run_id: UUID,
    cron_id: UUID,
    entrypoint: CronEntrypoint,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """Execute a cron spec and update the CronRun record.

    Expects the CronRun to already exist with status=RUNNING.
    Returns the executor result on success, None on failure.
    """
    if entrypoint not in CRON_REGISTRY:
        with get_db_session() as session:
            update_cron_run(
                session=session,
                run_id=run_id,
                status=CronStatus.ERROR,
                finished_at=datetime.now(timezone.utc),
                error=f"Invalid entrypoint '{entrypoint}'.",
            )
        return None

    spec = CRON_REGISTRY[entrypoint]

    try:
        execution_payload = spec.execution_payload_model(**payload)

        with get_db_session() as session:
            spec.execution_validator(execution_payload, db=session, cron_id=cron_id)
            result = await spec.executor(execution_payload, db=session, cron_id=cron_id)

        if isinstance(result, AsyncCronJobResult):
            with get_db_session() as session:
                update_cron_run(session=session, run_id=run_id, status=CronStatus.QUEUED)
            LOGGER.info(f"Cron job {cron_id} queued (run_id={result.run_id}, cron_run_id={result.cron_run_id})")
            return result

        with get_db_session() as session:
            update_cron_run(
                session=session,
                run_id=run_id,
                status=CronStatus.COMPLETED,
                finished_at=datetime.now(timezone.utc),
                result=result,
            )

        LOGGER.info(f"Cron run {run_id} for job {cron_id} completed successfully")
        return result

    except Exception as e:
        LOGGER.error(f"Cron run {run_id} for job {cron_id} failed: {e}")
        with get_db_session() as session:
            update_cron_run(
                session=session,
                run_id=run_id,
                status=CronStatus.ERROR,
                finished_at=datetime.now(timezone.utc),
                error=str(e),
            )
        raise

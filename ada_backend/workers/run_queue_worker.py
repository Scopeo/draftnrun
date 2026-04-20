import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

import sentry_sdk

from ada_backend.database.models import CallType, CronRun, CronStatus, EnvType, GraphRunner, ResponseFormat, RunStatus
from ada_backend.database.setup_db import get_db_session
from ada_backend.repositories import run_repository
from ada_backend.repositories.cron_repository import update_cron_run
from ada_backend.repositories.run_input_repository import save_run_input
from ada_backend.services.agent_runner_service import run_agent, run_env_agent
from ada_backend.services.run_service import _upload_result_to_s3, update_run_status
from ada_backend.services.tag_service import compose_tag_name
from ada_backend.utils.redis_client import publish_run_event
from ada_backend.workers.base_queue_worker import BaseQueueWorker
from engine.trace.span_context import reset_tracing_span, set_tracing_span
from settings import settings

LOGGER = logging.getLogger(__name__)


class RunQueueWorker(BaseQueueWorker):
    def __init__(self):
        super().__init__(
            queue_name=settings.REDIS_RUNS_QUEUE_NAME,
            worker_label="run-queue",
            trace_project_name="ada-backend-worker",
        )

    @property
    def required_payload_keys(self) -> tuple[str, ...]:
        return ("run_id", "project_id", "env", "input_data")

    def parse_item_id(self, item_payload: dict):
        return UUID(item_payload["run_id"])

    def recover_orphaned_item(self, item_payload: dict) -> None:
        run_id = UUID(item_payload["run_id"])
        with get_db_session() as session:
            run = run_repository.get_run(session, run_id)
            if not run:
                return
            current = run.status if isinstance(run.status, RunStatus) else RunStatus(str(run.status))
            if current == RunStatus.RUNNING:
                run_repository.update_run_status(session, run_id=run_id, status=RunStatus.PENDING)

    @staticmethod
    def _finalize_cron_run(cron_run_id: UUID | None, succeeded: bool, error_msg: str | None) -> None:
        if not cron_run_id:
            return
        terminal = (CronStatus.COMPLETED, CronStatus.ERROR)
        with get_db_session() as session:
            try:
                cron_run = session.query(CronRun).filter(CronRun.id == cron_run_id).first()
                if cron_run and cron_run.status in terminal:
                    LOGGER.debug("CronRun %s already %s, skipping finalize", cron_run_id, cron_run.status.value)
                    return
                update_cron_run(
                    session=session,
                    run_id=cron_run_id,
                    status=CronStatus.COMPLETED if succeeded else CronStatus.ERROR,
                    finished_at=datetime.now(timezone.utc),
                    error=error_msg,
                )
                LOGGER.info(
                    "CronRun %s marked %s",
                    cron_run_id,
                    "COMPLETED" if succeeded else "ERROR",
                )
            except Exception as e:
                LOGGER.error("Failed to update CronRun %s: %s", cron_run_id, e, exc_info=True)

    def process_payload(self, payload: dict, loop: asyncio.AbstractEventLoop) -> None:
        self._ensure_trace_manager()
        run_id = UUID(payload["run_id"])
        project_id = UUID(payload["project_id"])
        env_str = payload["env"]
        input_data = payload["input_data"]
        response_format = ResponseFormat(payload.get("response_format") or "s3_key")
        trigger_str = payload.get("trigger", CallType.API.value)
        cron_id = UUID(payload["cron_id"]) if payload.get("cron_id") else None
        cron_run_id = UUID(payload["cron_run_id"]) if payload.get("cron_run_id") else None

        with sentry_sdk.isolation_scope():
            reset_tracing_span()
            set_tracing_span(run_id=str(run_id))
            try:
                try:
                    env = EnvType(env_str) if env_str else None
                except ValueError:
                    LOGGER.warning("Invalid env in run %s: %s", run_id, env_str)
                    raise

                try:
                    call_type = CallType(trigger_str)
                except ValueError:
                    LOGGER.warning("Invalid trigger in run %s: %s, defaulting to API", run_id, trigger_str)
                    call_type = CallType.API

                if cron_id:
                    set_tracing_span(cron_id=str(cron_id))

                with get_db_session() as session:
                    run = run_repository.get_run(session, run_id)
                    if not run:
                        LOGGER.warning("Run %s not found, skipping", run_id)
                        self._finalize_cron_run(cron_run_id, False, f"Run {run_id} not found")
                        return
                    current = run.status if isinstance(run.status, RunStatus) else RunStatus(str(run.status))
                    if current != RunStatus.PENDING:
                        LOGGER.debug("Run %s already %s, skipping", run_id, current)
                        self._finalize_cron_run(cron_run_id, False, f"Run {run_id} already {current.value}")
                        return

                    if cron_run_id:
                        try:
                            update_cron_run(session=session, run_id=cron_run_id, status=CronStatus.RUNNING)
                        except Exception as e:
                            LOGGER.error("Failed to set CronRun %s to RUNNING: %s", cron_run_id, e, exc_info=True)
                            raise

                    retry_group = run.retry_group_id or run.id
                    save_run_input(session, retry_group_id=retry_group, project_id=project_id, input_data=input_data)

                    now = datetime.now(timezone.utc)
                    update_run_status(
                        session,
                        run_id=run_id,
                        project_id=project_id,
                        status=RunStatus.RUNNING,
                        started_at=now,
                    )

                async def event_callback(evt: dict):
                    publish_run_event(run_id, evt)

                async def execute_agent():
                    if env:
                        return await run_env_agent(
                            project_id=project_id,
                            env=env,
                            input_data=input_data,
                            call_type=call_type,
                            response_format=response_format,
                            event_callback=event_callback,
                        )
                    raw_gr_id = payload.get("graph_runner_id")
                    if not raw_gr_id:
                        raise ValueError("Payload has no env and no graph_runner_id")
                    graph_runner_id = UUID(raw_gr_id)
                    with get_db_session() as sess:
                        graph_runner = sess.get(GraphRunner, graph_runner_id)
                        if graph_runner is None:
                            raise ValueError(f"GraphRunner {graph_runner_id} not found for project {project_id}")
                        tag_name = compose_tag_name(graph_runner.tag_version, graph_runner.version_name)
                    return await run_agent(
                        project_id=project_id,
                        graph_runner_id=graph_runner_id,
                        input_data=input_data,
                        environment=None,
                        call_type=call_type,
                        tag_name=tag_name,
                        response_format=response_format,
                        event_callback=event_callback,
                    )

                result = loop.run_until_complete(execute_agent())
                result_id = _upload_result_to_s3(result, project_id=project_id, run_id=run_id)
                with get_db_session() as session:
                    update_run_status(
                        session,
                        run_id=run_id,
                        project_id=project_id,
                        status=RunStatus.COMPLETED,
                        trace_id=result.trace_id,
                        result_id=result_id,
                        finished_at=datetime.now(timezone.utc),
                    )
                publish_run_event(
                    run_id,
                    {"type": "run.completed", "trace_id": result.trace_id, "result_id": result_id},
                )
                LOGGER.info("Run %s completed", run_id)
                succeeded = True
                error_msg = None
            except Exception as e:
                LOGGER.exception("Run %s failed: %s", run_id, e)
                trace_id = getattr(e, "trace_id", None)
                try:
                    with get_db_session() as session:
                        update_run_status(
                            session,
                            run_id=run_id,
                            project_id=project_id,
                            status=RunStatus.FAILED,
                            error={"message": str(e), "type": type(e).__name__},
                            trace_id=trace_id,
                            finished_at=datetime.now(timezone.utc),
                        )
                except Exception as status_exc:
                    LOGGER.exception("Failed to update run %s to FAILED: %s", run_id, status_exc)

                try:
                    publish_run_event(
                        run_id,
                        {"type": "run.failed", "error": {"message": str(e), "type": type(e).__name__}},
                    )
                except Exception as event_exc:
                    LOGGER.exception("Failed to publish run.failed event for %s: %s", run_id, event_exc)
                succeeded = False
                error_msg = str(e)

            self._finalize_cron_run(cron_run_id, succeeded, error_msg)


_worker = RunQueueWorker()

_request_drain = _worker.request_drain
start_run_queue_worker_thread = _worker.start_thread

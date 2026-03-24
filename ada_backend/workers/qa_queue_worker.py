import asyncio
import logging
from uuid import UUID

from ada_backend.database.models import RunStatus
from ada_backend.database.setup_db import get_db_session
from ada_backend.repositories.qa_session_repository import get_qa_session, update_qa_session_status
from ada_backend.schemas.input_groundtruth_schema import QARunRequest
from ada_backend.services.qa.quality_assurance_service import run_qa_background
from ada_backend.workers.base_queue_worker import BaseQueueWorker
from settings import settings

LOGGER = logging.getLogger(__name__)


class QAQueueWorker(BaseQueueWorker):
    def __init__(self):
        super().__init__(
            queue_name=settings.REDIS_QA_QUEUE_NAME,
            worker_label="qa-queue",
            trace_project_name="ada-backend-qa-worker",
        )

    @property
    def required_payload_keys(self) -> tuple[str, ...]:
        return ("session_id", "project_id", "dataset_id", "run_request")

    def parse_item_id(self, item_payload: dict):
        return UUID(item_payload["session_id"])

    def recover_orphaned_item(self, item_payload: dict) -> None:
        session_id = UUID(item_payload["session_id"])
        with get_db_session() as session:
            qa_session = get_qa_session(session, session_id)
            if not qa_session:
                return
            current = (
                qa_session.status if isinstance(qa_session.status, RunStatus) else RunStatus(str(qa_session.status))
            )
            if current == RunStatus.RUNNING:
                update_qa_session_status(session, session_id, status=RunStatus.PENDING)

    def process_payload(self, payload: dict, loop: asyncio.AbstractEventLoop) -> None:
        self._ensure_trace_manager()
        session_id = UUID(payload["session_id"])
        project_id = UUID(payload["project_id"])
        dataset_id = UUID(payload["dataset_id"])
        run_request = QARunRequest(**payload["run_request"])

        with get_db_session() as session:
            qa_session = get_qa_session(session, session_id)
            if not qa_session:
                LOGGER.warning("QA session %s not found, skipping", session_id)
                return
            current = (
                qa_session.status if isinstance(qa_session.status, RunStatus) else RunStatus(str(qa_session.status))
            )
            if current != RunStatus.PENDING:
                LOGGER.debug("QA session %s already %s, skipping", session_id, current)
                return

        async def execute():
            await run_qa_background(session_id, project_id, dataset_id, run_request)

        loop.run_until_complete(execute())
        LOGGER.info("QA session %s completed via worker", session_id)


_worker = QAQueueWorker()

_request_qa_drain = _worker.request_drain
start_qa_queue_worker_thread = _worker.start_thread

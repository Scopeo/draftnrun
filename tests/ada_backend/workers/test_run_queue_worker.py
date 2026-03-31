import asyncio
from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from ada_backend.database.models import RunStatus
from ada_backend.workers.run_queue_worker import RunQueueWorker


@pytest.fixture
def worker():
    with patch.object(RunQueueWorker, "__init__", lambda self: None):
        w = RunQueueWorker.__new__(RunQueueWorker)
        w._trace_manager = None
        return w


@pytest.fixture
def loop():
    lp = asyncio.new_event_loop()
    yield lp
    lp.close()


class TestProcessPayloadGraphRunnerNotFound:
    def test_raises_when_graph_runner_missing(self, worker, loop):
        run_id = uuid4()
        project_id = uuid4()
        gr_id = uuid4()

        payload = {
            "run_id": str(run_id),
            "project_id": str(project_id),
            "env": "",
            "input_data": {"text": "hello"},
            "graph_runner_id": str(gr_id),
        }

        mock_run = MagicMock()
        mock_run.status = "pending"

        sessions = []

        @contextmanager
        def fake_db_session():
            s = MagicMock()
            sessions.append(s)
            s.get.return_value = None
            yield s

        with (
            patch.object(worker, "_ensure_trace_manager"),
            patch("ada_backend.workers.run_queue_worker.get_db_session", side_effect=fake_db_session),
            patch("ada_backend.workers.run_queue_worker.run_repository") as mock_run_repo,
            patch("ada_backend.workers.run_queue_worker.update_run_status") as mock_update,
            patch("ada_backend.workers.run_queue_worker.publish_run_event"),
        ):
            mock_run_repo.get_run.return_value = mock_run

            worker.process_payload(payload, loop)

            failed_calls = [
                c for c in mock_update.call_args_list if c.kwargs.get("status") == RunStatus.FAILED
            ]
            assert failed_calls, "Expected run to be marked as FAILED"
            error = failed_calls[0].kwargs["error"]
            assert str(gr_id) in error["message"]
            assert str(project_id) in error["message"]

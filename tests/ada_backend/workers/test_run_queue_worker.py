import asyncio
from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from ada_backend.database.models import RunStatus
from ada_backend.workers.run_queue_worker import RunQueueWorker
from engine.trace.span_context import get_tracing_span


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


@pytest.fixture(autouse=True)
def reset_tracing_context():
    from engine.trace.span_context import _tracing_context

    token = _tracing_context.set(None)
    yield
    _tracing_context.reset(token)


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
            patch("ada_backend.workers.run_queue_worker.save_run_input"),
        ):
            mock_run_repo.get_run.return_value = mock_run

            worker.process_payload(payload, loop)

            failed_calls = [c for c in mock_update.call_args_list if c.kwargs.get("status") == RunStatus.FAILED]
            assert failed_calls, "Expected run to be marked as FAILED"
            error = failed_calls[0].kwargs["error"]
            assert str(gr_id) in error["message"]
            assert str(project_id) in error["message"]


class TestProcessPayloadPersistsInput:
    def test_saves_run_input_before_execution(self, worker, loop):
        run_id = uuid4()
        project_id = uuid4()
        retry_group_id = uuid4()

        payload = {
            "run_id": str(run_id),
            "project_id": str(project_id),
            "env": "production",
            "input_data": {"text": "hello"},
            "trigger": "api",
        }

        mock_run = MagicMock()
        mock_run.status = "pending"
        mock_run.retry_group_id = retry_group_id
        mock_run.id = run_id

        @contextmanager
        def fake_db_session():
            s = MagicMock()
            s.get.return_value = None
            yield s

        with (
            patch.object(worker, "_ensure_trace_manager"),
            patch("ada_backend.workers.run_queue_worker.get_db_session", side_effect=fake_db_session),
            patch("ada_backend.workers.run_queue_worker.run_repository") as mock_run_repo,
            patch("ada_backend.workers.run_queue_worker.update_run_status"),
            patch("ada_backend.workers.run_queue_worker.publish_run_event"),
            patch("ada_backend.workers.run_queue_worker.save_run_input") as mock_save,
            patch("ada_backend.workers.run_queue_worker.run_env_agent", side_effect=Exception("boom")),
        ):
            mock_run_repo.get_run.return_value = mock_run

            worker.process_payload(payload, loop)

            mock_save.assert_called_once()
            _, kwargs = mock_save.call_args
            assert kwargs["retry_group_id"] == retry_group_id
            assert kwargs["project_id"] == project_id
            assert kwargs["input_data"] == {"text": "hello"}

    def test_uses_run_id_as_fallback_when_no_retry_group(self, worker, loop):
        run_id = uuid4()
        project_id = uuid4()

        payload = {
            "run_id": str(run_id),
            "project_id": str(project_id),
            "env": "production",
            "input_data": {"key": "val"},
            "trigger": "api",
        }

        mock_run = MagicMock()
        mock_run.status = "pending"
        mock_run.retry_group_id = None
        mock_run.id = run_id

        @contextmanager
        def fake_db_session():
            yield MagicMock()

        with (
            patch.object(worker, "_ensure_trace_manager"),
            patch("ada_backend.workers.run_queue_worker.get_db_session", side_effect=fake_db_session),
            patch("ada_backend.workers.run_queue_worker.run_repository") as mock_run_repo,
            patch("ada_backend.workers.run_queue_worker.update_run_status"),
            patch("ada_backend.workers.run_queue_worker.publish_run_event"),
            patch("ada_backend.workers.run_queue_worker.save_run_input") as mock_save,
            patch("ada_backend.workers.run_queue_worker.run_env_agent", side_effect=Exception("boom")),
        ):
            mock_run_repo.get_run.return_value = mock_run

            worker.process_payload(payload, loop)

            _, kwargs = mock_save.call_args
            assert kwargs["retry_group_id"] == run_id


class TestProcessPayloadTracing:
    def test_sets_run_id_inside_fresh_isolation_scope(self, worker, loop):
        run_id = uuid4()
        project_id = uuid4()

        payload = {
            "run_id": str(run_id),
            "project_id": str(project_id),
            "env": "production",
            "input_data": {"text": "hello"},
            "trigger": "api",
        }

        mock_run = MagicMock()
        mock_run.status = "pending"
        mock_run.retry_group_id = None
        mock_run.id = run_id

        observed = {"entered_scope": False, "run_id": None}

        @contextmanager
        def fake_db_session():
            yield MagicMock()

        @contextmanager
        def fake_isolation_scope():
            observed["entered_scope"] = True
            yield

        async def fake_run_env_agent(**kwargs):
            params = get_tracing_span()
            observed["run_id"] = params.run_id if params else None
            raise Exception("boom")

        with (
            patch.object(worker, "_ensure_trace_manager"),
            patch("ada_backend.workers.run_queue_worker.get_db_session", side_effect=fake_db_session),
            patch("ada_backend.workers.run_queue_worker.run_repository") as mock_run_repo,
            patch("ada_backend.workers.run_queue_worker.update_run_status"),
            patch("ada_backend.workers.run_queue_worker.publish_run_event"),
            patch("ada_backend.workers.run_queue_worker.save_run_input"),
            patch("ada_backend.workers.run_queue_worker.sentry_sdk.isolation_scope", side_effect=fake_isolation_scope),
            patch("ada_backend.workers.run_queue_worker.run_env_agent", side_effect=fake_run_env_agent),
        ):
            mock_run_repo.get_run.return_value = mock_run

            worker.process_payload(payload, loop)

        assert observed["entered_scope"] is True
        assert observed["run_id"] == str(run_id)

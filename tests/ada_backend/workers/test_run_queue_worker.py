import asyncio
from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from ada_backend.database.models import CronStatus, RunStatus
from ada_backend.workers.run_queue_worker import RunQueueWorker
from engine.trace.span_context import get_tracing_span, set_tracing_span


@pytest.fixture(autouse=True)
def reset_tracing_context():
    from engine.trace.span_context import _tracing_context

    token = _tracing_context.set(None)
    yield
    _tracing_context.reset(token)


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


def _make_pending_run(run_id, retry_group_id=None):
    mock_run = MagicMock()
    mock_run.status = "pending"
    mock_run.retry_group_id = retry_group_id
    mock_run.id = run_id
    return mock_run


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

    def test_resets_stale_context_from_previous_run(self, worker, loop):
        set_tracing_span(cron_id="cron-stale", project_id="proj-stale", organization_id="org-stale")

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

        observed = {"cron_id": "not-set", "project_id": "not-set", "organization_id": "not-set"}

        @contextmanager
        def fake_db_session():
            yield MagicMock()

        async def fake_run_env_agent(**kwargs):
            params = get_tracing_span()
            assert params is not None
            observed["cron_id"] = params.cron_id
            observed["project_id"] = params.project_id
            observed["organization_id"] = params.organization_id
            raise Exception("boom")

        @contextmanager
        def fake_isolation_scope():
            yield

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

        assert observed["cron_id"] is None
        assert observed["project_id"] == ""
        assert observed["organization_id"] == ""


class TestProcessPayloadCronHandling:
    def test_sets_cron_id_in_tracing_context(self, worker, loop):
        run_id = uuid4()
        cron_id = uuid4()
        captured = {}

        async def fake_agent(**kwargs):
            span = get_tracing_span()
            captured["cron_id"] = span.cron_id if span else None
            result = MagicMock()
            result.trace_id = "trace-123"
            return result

        payload = {
            "run_id": str(run_id),
            "project_id": str(uuid4()),
            "env": "production",
            "input_data": {"text": "hello"},
            "trigger": "cron",
            "cron_id": str(cron_id),
        }

        @contextmanager
        def fake_db_session():
            yield MagicMock()

        with (
            patch.object(worker, "_ensure_trace_manager"),
            patch("ada_backend.workers.run_queue_worker.get_db_session", side_effect=fake_db_session),
            patch("ada_backend.workers.run_queue_worker.run_repository") as mock_run_repo,
            patch("ada_backend.workers.run_queue_worker.update_run_status"),
            patch("ada_backend.workers.run_queue_worker.publish_run_event"),
            patch("ada_backend.workers.run_queue_worker.save_run_input"),
            patch("ada_backend.workers.run_queue_worker._upload_result_to_s3", return_value="s3-key"),
            patch("ada_backend.workers.run_queue_worker.run_env_agent", side_effect=fake_agent),
        ):
            mock_run_repo.get_run.return_value = _make_pending_run(run_id)
            worker.process_payload(payload, loop)

        assert captured["cron_id"] == str(cron_id)

    def test_updates_cron_run_status_on_success(self, worker, loop):
        run_id = uuid4()
        cron_run_id = uuid4()

        payload = {
            "run_id": str(run_id),
            "project_id": str(uuid4()),
            "env": "production",
            "input_data": {"text": "hello"},
            "trigger": "cron",
            "cron_id": str(uuid4()),
            "cron_run_id": str(cron_run_id),
        }

        async def fake_agent(**kwargs):
            result = MagicMock()
            result.trace_id = "trace-123"
            return result

        @contextmanager
        def fake_db_session():
            yield MagicMock()

        with (
            patch.object(worker, "_ensure_trace_manager"),
            patch("ada_backend.workers.run_queue_worker.get_db_session", side_effect=fake_db_session),
            patch("ada_backend.workers.run_queue_worker.run_repository") as mock_run_repo,
            patch("ada_backend.workers.run_queue_worker.update_run_status"),
            patch("ada_backend.workers.run_queue_worker.publish_run_event"),
            patch("ada_backend.workers.run_queue_worker.save_run_input"),
            patch("ada_backend.workers.run_queue_worker._upload_result_to_s3", return_value="s3-key"),
            patch("ada_backend.workers.run_queue_worker.run_env_agent", side_effect=fake_agent),
            patch("ada_backend.workers.run_queue_worker.update_cron_run") as mock_cron,
        ):
            mock_run_repo.get_run.return_value = _make_pending_run(run_id)
            worker.process_payload(payload, loop)

        running_call = mock_cron.call_args_list[0]
        assert running_call.kwargs["status"] == CronStatus.RUNNING

        completed_call = mock_cron.call_args_list[1]
        assert completed_call.kwargs["status"] == CronStatus.COMPLETED
        assert completed_call.kwargs["error"] is None

    def test_updates_cron_run_status_on_failure(self, worker, loop):
        run_id = uuid4()
        cron_run_id = uuid4()

        payload = {
            "run_id": str(run_id),
            "project_id": str(uuid4()),
            "env": "production",
            "input_data": {"text": "hello"},
            "trigger": "cron",
            "cron_id": str(uuid4()),
            "cron_run_id": str(cron_run_id),
        }

        @contextmanager
        def fake_db_session():
            yield MagicMock()

        with (
            patch.object(worker, "_ensure_trace_manager"),
            patch("ada_backend.workers.run_queue_worker.get_db_session", side_effect=fake_db_session),
            patch("ada_backend.workers.run_queue_worker.run_repository") as mock_run_repo,
            patch("ada_backend.workers.run_queue_worker.update_run_status"),
            patch("ada_backend.workers.run_queue_worker.publish_run_event"),
            patch("ada_backend.workers.run_queue_worker.save_run_input"),
            patch("ada_backend.workers.run_queue_worker.run_env_agent", side_effect=Exception("agent crashed")),
            patch("ada_backend.workers.run_queue_worker.update_cron_run") as mock_cron,
        ):
            mock_run_repo.get_run.return_value = _make_pending_run(run_id)
            worker.process_payload(payload, loop)

        error_call = mock_cron.call_args_list[1]
        assert error_call.kwargs["status"] == CronStatus.ERROR
        assert "agent crashed" in error_call.kwargs["error"]

    def test_finalizes_cron_when_run_not_found(self, worker, loop):
        cron_run_id = uuid4()

        payload = {
            "run_id": str(uuid4()),
            "project_id": str(uuid4()),
            "env": "production",
            "input_data": {"text": "hello"},
            "trigger": "cron",
            "cron_run_id": str(cron_run_id),
        }

        @contextmanager
        def fake_db_session():
            yield MagicMock()

        with (
            patch.object(worker, "_ensure_trace_manager"),
            patch("ada_backend.workers.run_queue_worker.get_db_session", side_effect=fake_db_session),
            patch("ada_backend.workers.run_queue_worker.run_repository") as mock_run_repo,
            patch("ada_backend.workers.run_queue_worker.update_cron_run") as mock_cron,
        ):
            mock_run_repo.get_run.return_value = None
            worker.process_payload(payload, loop)

        assert mock_cron.call_count == 1
        assert mock_cron.call_args_list[0].kwargs["status"] == CronStatus.ERROR

    def test_finalizes_cron_when_run_already_completed(self, worker, loop):
        run_id = uuid4()
        cron_run_id = uuid4()

        payload = {
            "run_id": str(run_id),
            "project_id": str(uuid4()),
            "env": "production",
            "input_data": {"text": "hello"},
            "trigger": "cron",
            "cron_run_id": str(cron_run_id),
        }

        completed_run = MagicMock()
        completed_run.status = RunStatus.COMPLETED
        completed_run.id = run_id

        @contextmanager
        def fake_db_session():
            yield MagicMock()

        with (
            patch.object(worker, "_ensure_trace_manager"),
            patch("ada_backend.workers.run_queue_worker.get_db_session", side_effect=fake_db_session),
            patch("ada_backend.workers.run_queue_worker.run_repository") as mock_run_repo,
            patch("ada_backend.workers.run_queue_worker.update_cron_run") as mock_cron,
        ):
            mock_run_repo.get_run.return_value = completed_run
            worker.process_payload(payload, loop)

        assert mock_cron.call_count == 1
        error_call = mock_cron.call_args_list[0]
        assert error_call.kwargs["status"] == CronStatus.ERROR
        assert "already" in error_call.kwargs["error"]


class TestFinalizeCronRunTerminalGuard:
    def test_skips_finalize_when_cron_run_already_completed(self):
        cron_run_id = uuid4()
        mock_cron_run = MagicMock()
        mock_cron_run.status = CronStatus.COMPLETED

        @contextmanager
        def fake_db_session():
            s = MagicMock()
            s.query.return_value.filter.return_value.first.return_value = mock_cron_run
            yield s

        with (
            patch("ada_backend.workers.run_queue_worker.get_db_session", side_effect=fake_db_session),
            patch("ada_backend.workers.run_queue_worker.update_cron_run") as mock_update,
        ):
            RunQueueWorker._finalize_cron_run(cron_run_id, False, "some error")

        mock_update.assert_not_called()

    def test_skips_finalize_when_cron_run_already_errored(self):
        cron_run_id = uuid4()
        mock_cron_run = MagicMock()
        mock_cron_run.status = CronStatus.ERROR

        @contextmanager
        def fake_db_session():
            s = MagicMock()
            s.query.return_value.filter.return_value.first.return_value = mock_cron_run
            yield s

        with (
            patch("ada_backend.workers.run_queue_worker.get_db_session", side_effect=fake_db_session),
            patch("ada_backend.workers.run_queue_worker.update_cron_run") as mock_update,
        ):
            RunQueueWorker._finalize_cron_run(cron_run_id, True, None)

        mock_update.assert_not_called()

    def test_proceeds_when_cron_run_is_running(self):
        cron_run_id = uuid4()
        mock_cron_run = MagicMock()
        mock_cron_run.status = CronStatus.RUNNING

        @contextmanager
        def fake_db_session():
            s = MagicMock()
            s.query.return_value.filter.return_value.first.return_value = mock_cron_run
            yield s

        with (
            patch("ada_backend.workers.run_queue_worker.get_db_session", side_effect=fake_db_session),
            patch("ada_backend.workers.run_queue_worker.update_cron_run") as mock_update,
        ):
            RunQueueWorker._finalize_cron_run(cron_run_id, True, None)

        mock_update.assert_called_once()
        assert mock_update.call_args.kwargs["status"] == CronStatus.COMPLETED

    def test_proceeds_when_cron_run_not_found(self):
        cron_run_id = uuid4()

        @contextmanager
        def fake_db_session():
            s = MagicMock()
            s.query.return_value.filter.return_value.first.return_value = None
            yield s

        with (
            patch("ada_backend.workers.run_queue_worker.get_db_session", side_effect=fake_db_session),
            patch("ada_backend.workers.run_queue_worker.update_cron_run") as mock_update,
        ):
            RunQueueWorker._finalize_cron_run(cron_run_id, False, "run not found")

        mock_update.assert_called_once()
        assert mock_update.call_args.kwargs["status"] == CronStatus.ERROR

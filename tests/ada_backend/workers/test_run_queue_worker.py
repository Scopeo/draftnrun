import asyncio
import json
from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from ada_backend.database.models import CronStatus, RunStatus
from ada_backend.workers.base_queue_worker import (
    _HEARTBEAT_TTL,
    _MAX_ORPHAN_FOLLOW_UPS,
    _ORPHAN_FOLLOW_UP_DELAY,
    BaseQueueWorker,
)
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


class TestPeriodicOrphanRecovery:
    """Regression: startup scan misses dead workers whose heartbeat hasn't expired yet.
    The periodic scan (after _ORPHAN_SCAN_INTERVAL) must recover them."""

    def test_periodic_scan_recovers_orphan_after_heartbeat_expires(self):
        queue_name = "test_queue"
        dead_worker_id = "dead-worker-aaa"
        processing_key = BaseQueueWorker._processing_queue_key(queue_name, dead_worker_id)
        heartbeat_key = BaseQueueWorker._heartbeat_key(queue_name, dead_worker_id)
        orphan_payload = json.dumps({
            "run_id": str(uuid4()),
            "project_id": str(uuid4()),
            "env": "production",
            "input_data": {},
        })

        client = MagicMock()

        heartbeat_alive = True

        def fake_exists(key):
            if key == heartbeat_key:
                return heartbeat_alive
            return False

        client.exists.side_effect = fake_exists
        client.scan.return_value = (0, [processing_key])
        client.rpop.side_effect = [orphan_payload.encode(), None]

        with patch.object(RunQueueWorker, "__init__", lambda self: None):
            w = RunQueueWorker.__new__(RunQueueWorker)
            w.queue_name = queue_name
            w.worker_label = "test"

        own_processing = BaseQueueWorker._processing_queue_key(queue_name, "live-worker")

        w._recover_orphaned_processing_queues(client, own_processing)
        client.rpop.assert_not_called()

        heartbeat_alive = False
        client.scan.return_value = (0, [processing_key])
        client.rpop.side_effect = [orphan_payload.encode(), None]

        w._recover_orphaned_processing_queues(client, own_processing)
        client.rpop.assert_called()
        client.lpush.assert_called_once_with(queue_name, orphan_payload.encode())

    def test_worker_loop_triggers_periodic_scan(self):
        queue_name = "test_queue"
        scan_call_count = 0

        with patch.object(RunQueueWorker, "__init__", lambda self: None):
            w = RunQueueWorker.__new__(RunQueueWorker)
            w.queue_name = queue_name
            w.worker_label = "test"
            w._trace_manager = None
            w._trace_project_name = "test"
            w._drain_requested = MagicMock()

        drain_calls = [False, False, False, True]
        w._drain_requested.is_set = MagicMock(side_effect=drain_calls)

        client = MagicMock()
        client.brpoplpush.return_value = None
        client.rpoplpush.return_value = None

        def counting_recover(self_inner, cl, own_pq):
            nonlocal scan_call_count
            scan_call_count += 1

        t0 = 1000.0

        with (
            patch("ada_backend.workers.base_queue_worker.get_redis_client", return_value=client),
            patch.object(
                BaseQueueWorker,
                "_recover_orphaned_processing_queues",
                counting_recover,
            ),
            patch("ada_backend.workers.base_queue_worker.time") as mock_time,
            patch("ada_backend.workers.base_queue_worker.threading") as mock_threading,
        ):
            mock_time.monotonic = MagicMock(
                side_effect=[
                    t0,
                    t0 + _ORPHAN_FOLLOW_UP_DELAY + 1,
                    t0 + _ORPHAN_FOLLOW_UP_DELAY + 2,
                ]
            )
            mock_threading.Event.return_value = MagicMock()
            mock_threading.Thread.return_value = MagicMock()

            w._worker_loop()

        assert scan_call_count >= 2

    def test_follow_up_scans_stop_after_cap(self):
        queue_name = "test_queue"
        scan_call_count = 0

        with patch.object(RunQueueWorker, "__init__", lambda self: None):
            w = RunQueueWorker.__new__(RunQueueWorker)
            w.queue_name = queue_name
            w.worker_label = "test"
            w._trace_manager = None
            w._trace_project_name = "test"
            w._drain_requested = MagicMock()

        iterations = _MAX_ORPHAN_FOLLOW_UPS + 3
        drain_calls = [False] * iterations + [True]
        w._drain_requested.is_set = MagicMock(side_effect=drain_calls)

        client = MagicMock()
        client.brpoplpush.return_value = None
        client.rpoplpush.return_value = None

        def counting_recover(self_inner, cl, own_pq):
            nonlocal scan_call_count
            scan_call_count += 1

        t0 = 1000.0
        timestamps = [t0] + [t0 + _ORPHAN_FOLLOW_UP_DELAY * (i + 1) for i in range(iterations)]

        with (
            patch("ada_backend.workers.base_queue_worker.get_redis_client", return_value=client),
            patch.object(
                BaseQueueWorker,
                "_recover_orphaned_processing_queues",
                counting_recover,
            ),
            patch("ada_backend.workers.base_queue_worker.time") as mock_time,
            patch("ada_backend.workers.base_queue_worker.threading") as mock_threading,
        ):
            mock_time.monotonic = MagicMock(side_effect=timestamps)
            mock_threading.Event.return_value = MagicMock()
            mock_threading.Thread.return_value = MagicMock()

            w._worker_loop()

        assert scan_call_count == 1 + _MAX_ORPHAN_FOLLOW_UPS

    def test_follow_up_delay_covers_heartbeat_ttl(self):
        assert _ORPHAN_FOLLOW_UP_DELAY >= _HEARTBEAT_TTL

    def test_recover_resets_db_before_enqueueing(self):
        """The DB status must be reset to PENDING before the item is pushed to the
        main queue, otherwise a concurrent worker can grab it, see RUNNING, and
        silently discard it."""
        queue_name = "test_queue"
        dead_worker_id = "dead-worker-race"
        processing_key = BaseQueueWorker._processing_queue_key(queue_name, dead_worker_id)
        run_id = uuid4()
        orphan_payload = json.dumps({
            "run_id": str(run_id),
            "project_id": str(uuid4()),
            "env": "production",
            "input_data": {},
        })

        client = MagicMock()
        client.exists.return_value = False
        client.scan.return_value = (0, [processing_key])
        client.rpop.side_effect = [orphan_payload.encode(), None]

        call_order = []
        original_lpush = client.lpush

        def tracking_lpush(*args, **kwargs):
            call_order.append("lpush")
            return original_lpush(*args, **kwargs)

        client.lpush = MagicMock(side_effect=tracking_lpush)

        with patch.object(RunQueueWorker, "__init__", lambda self: None):
            w = RunQueueWorker.__new__(RunQueueWorker)
            w.queue_name = queue_name
            w.worker_label = "test"

        def tracking_recover(item_payload):
            call_order.append("recover")

        with patch.object(w, "recover_orphaned_item", side_effect=tracking_recover):
            own_processing = BaseQueueWorker._processing_queue_key(queue_name, "live-worker")
            w._recover_orphaned_processing_queues(client, own_processing)

        assert call_order == ["recover", "lpush"], (
            f"recover_orphaned_item must be called before lpush, got: {call_order}"
        )

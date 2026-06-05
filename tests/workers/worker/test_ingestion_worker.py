import signal
import subprocess
import threading
import time
from unittest.mock import MagicMock, patch

import pytest
import redis

from workers.worker import main as worker_main
from workers.worker.base_worker import ProcessTaskOutcome


@pytest.fixture
def worker():
    w = worker_main.Worker.__new__(worker_main.Worker)
    w.stream_name = worker_main.STREAM_NAME
    w.max_concurrent = 1
    w.current_threads = 0
    w.worker_type = "redis_ingestion"
    return w


def _make_payload(**overrides):
    base = {
        "ingestion_id": "ing-test",
        "organization_id": "org-test",
        "task_id": "task-test",
        "source_type": "local",
        "source_name": "test-source",
        "source_attributes": {"list_of_files_from_local_folder": []},
    }
    base.update(overrides)
    return base


class TestSubprocessTimeout:
    def test_timeout_env_default_is_1800(self):
        assert worker_main.SUBPROCESS_TIMEOUT_S == 1800


class TestFatalErrorTypes:
    @pytest.mark.parametrize(
        "error_type",
        [
            "Out of Memory",
            "Environment Error",
            "Module Not Found Error",
            "Google AI API Error",
            "pyarrow_incompatible",
        ],
    )
    def test_deterministic_errors_are_fatal(self, worker, error_type):
        assert error_type in worker._FATAL_ERROR_TYPES

    @pytest.mark.parametrize(
        "error_type",
        [
            "SSL Connection Error",
            "Subprocess Error",
            "TimeoutError",
            None,
        ],
    )
    def test_transient_errors_are_not_fatal(self, worker, error_type):
        assert error_type not in worker._FATAL_ERROR_TYPES


class TestParseErrorMessage:
    def test_oom_detected(self, worker):
        result = worker._parse_error_message("MemoryError: cannot allocate")
        assert result["error_type"] == "Out of Memory"

    def test_oom_allocate_variant(self, worker):
        result = worker._parse_error_message("OSError: Cannot allocate memory")
        assert result["error_type"] == "Out of Memory"

    def test_fernet_key_missing(self, worker):
        result = worker._parse_error_message("RuntimeError: FERNET_KEY is not set")
        assert result["error_type"] == "Environment Error"

    def test_google_api_missing(self, worker):
        result = worker._parse_error_message("Missing key inputs argument!")
        assert result["error_type"] == "Google AI API Error"

    def test_module_not_found(self, worker):
        result = worker._parse_error_message("ModuleNotFoundError: No module named 'foobar'")
        assert result["error_type"] == "Module Not Found Error"

    def test_pyarrow_incompatible(self, worker):
        result = worker._parse_error_message("pyarrow has an incompatible version 12.0")
        assert result["error_type"] == "pyarrow_incompatible"

    def test_ssl_error(self, worker):
        result = worker._parse_error_message("SSL: WRONG_VERSION_NUMBER")
        assert result["error_type"] == "SSL Connection Error"

    def test_generic_exception_fallback(self, worker):
        result = worker._parse_error_message("ValueError: bad input data")
        assert result["error_type"] == "ValueError"
        assert result["error_message"] == "bad input data"

    def test_empty_stderr(self, worker):
        result = worker._parse_error_message("")
        assert result["error_type"] is None


class TestFatalVsRetryOutcome:
    @pytest.mark.parametrize(
        "stderr_text,expected_error_type",
        [
            ("MemoryError: cannot allocate", "Out of Memory"),
            ("RuntimeError: FERNET_KEY is not set", "Environment Error"),
            ("ModuleNotFoundError: No module named 'foo'", "Module Not Found Error"),
            ("Missing key inputs argument!", "Google AI API Error"),
            ("pyarrow has an incompatible version 12", "pyarrow_incompatible"),
        ],
    )
    def test_fatal_errors_produce_fatal_outcome(self, worker, stderr_text, expected_error_type):
        error_summary = worker._parse_error_message(stderr_text)
        assert error_summary["error_type"] == expected_error_type
        assert error_summary["error_type"] in worker._FATAL_ERROR_TYPES

    @pytest.mark.parametrize(
        "stderr_text",
        [
            "SSL: WRONG_VERSION_NUMBER",
            "ConnectionError: timed out",
            "ValueError: bad input",
        ],
    )
    def test_transient_errors_produce_retry_outcome(self, worker, stderr_text):
        error_summary = worker._parse_error_message(stderr_text)
        assert error_summary["error_type"] not in worker._FATAL_ERROR_TYPES


class TestTaskStatusOnRetry:
    """Regression: retryable errors must reset the task to PENDING, not leave it FAILED."""

    def _run_process_task(self, worker, stderr_text: str, returncode: int = 1):
        mock_process = MagicMock()
        mock_process.returncode = returncode
        mock_process.stdout = MagicMock()
        mock_process.stderr = MagicMock()
        mock_process.poll = MagicMock(side_effect=[None, 0])
        mock_process.stdout.fileno.return_value = 10
        mock_process.stderr.fileno.return_value = 11
        mock_process.stdout.read.return_value = b""
        mock_process.stderr.read.return_value = stderr_text.encode()

        with (
            patch("subprocess.Popen", return_value=mock_process),
            patch("select.select", return_value=([], [], [])),
            patch("fcntl.fcntl"),
            patch.object(worker, "_update_task_status_to_failed") as mock_failed,
            patch.object(worker, "_reset_task_status_to_pending") as mock_pending,
        ):
            outcome = worker.process_task(_make_payload())
        return outcome, mock_failed, mock_pending

    def test_retryable_error_resets_to_pending(self, worker):
        outcome, mock_failed, mock_pending = self._run_process_task(
            worker, "httpx.HTTPStatusError: Client error '404 Not Found'"
        )
        assert outcome == ProcessTaskOutcome.FAIL_RETRY
        mock_pending.assert_called_once()
        mock_failed.assert_not_called()

    def test_fatal_error_marks_failed(self, worker):
        outcome, mock_failed, mock_pending = self._run_process_task(
            worker, "MemoryError: cannot allocate"
        )
        assert outcome == ProcessTaskOutcome.FAIL_FATAL_ACK
        mock_failed.assert_called_once()
        mock_pending.assert_not_called()


class TestPELHeartbeat:
    """The heartbeat refreshes the PEL idle timer without incrementing times_delivered.

    Regression for: long-running ingestion subprocesses being dead-lettered as
    "failed after 3 attempts" while their subprocess kept ingesting.
    """

    def test_heartbeat_uses_xclaim_with_justid(self, worker, monkeypatch):
        recorded = []

        def fake_xclaim(*args, **kwargs):
            recorded.append(kwargs)
            return []

        monkeypatch.setattr(worker_main.redis_client, "xclaim", fake_xclaim)
        monkeypatch.setattr(worker, "_consumer_name", lambda: "test-consumer")

        stop_event = threading.Event()
        threading.Timer(0.2, stop_event.set).start()

        worker._pel_heartbeat_loop(
            message_id="1234567-0",
            stop_event=stop_event,
            interval_s=0.05,
            max_duration_s=10.0,
        )

        assert len(recorded) >= 2
        for kwargs in recorded:
            assert kwargs["justid"] is True
            assert kwargs["min_idle_time"] == 0
            assert kwargs["message_ids"] == ["1234567-0"]

    def test_heartbeat_never_increments_delivery_count(self, worker, monkeypatch):
        """No code path may issue xclaim/xautoclaim WITHOUT justid during the heartbeat."""
        recorded_calls = []

        def fake_xclaim(*args, **kwargs):
            recorded_calls.append(("xclaim", kwargs))
            return []

        def fake_xautoclaim(*args, **kwargs):
            recorded_calls.append(("xautoclaim", kwargs))
            return ("0-0", [], [])

        monkeypatch.setattr(worker_main.redis_client, "xclaim", fake_xclaim)
        monkeypatch.setattr(worker_main.redis_client, "xautoclaim", fake_xautoclaim)
        monkeypatch.setattr(worker, "_consumer_name", lambda: "test-consumer")

        stop_event = threading.Event()
        threading.Timer(0.15, stop_event.set).start()

        worker._pel_heartbeat_loop(
            message_id="msg-id",
            stop_event=stop_event,
            interval_s=0.05,
            max_duration_s=10.0,
        )

        assert recorded_calls, "expected at least one heartbeat call"
        for name, kwargs in recorded_calls:
            assert name == "xclaim", f"unexpected redis call during heartbeat: {name}"
            assert kwargs.get("justid") is True

    def test_heartbeat_tolerates_redis_response_error(self, worker, monkeypatch):
        call_count = {"n": 0}

        def flaky_xclaim(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise redis.ResponseError("NOGROUP No such group")
            return []

        monkeypatch.setattr(worker_main.redis_client, "xclaim", flaky_xclaim)
        monkeypatch.setattr(worker, "_consumer_name", lambda: "test-consumer")

        stop_event = threading.Event()
        threading.Timer(0.2, stop_event.set).start()

        worker._pel_heartbeat_loop(
            message_id="msg-id",
            stop_event=stop_event,
            interval_s=0.05,
            max_duration_s=10.0,
        )

        assert call_count["n"] >= 2

    def test_heartbeat_tolerates_redis_connection_error(self, worker, monkeypatch):
        call_count = {"n": 0}

        def flaky_xclaim(*args, **kwargs):
            call_count["n"] += 1
            raise redis.ConnectionError("disconnected")

        monkeypatch.setattr(worker_main.redis_client, "xclaim", flaky_xclaim)
        monkeypatch.setattr(worker, "_consumer_name", lambda: "test-consumer")

        stop_event = threading.Event()
        threading.Timer(0.15, stop_event.set).start()

        worker._pel_heartbeat_loop(
            message_id="msg-id",
            stop_event=stop_event,
            interval_s=0.05,
            max_duration_s=10.0,
        )

        assert call_count["n"] >= 2

    def test_heartbeat_respects_max_duration(self, worker, monkeypatch):
        monkeypatch.setattr(worker_main.redis_client, "xclaim", MagicMock(return_value=[]))
        monkeypatch.setattr(worker, "_consumer_name", lambda: "test-consumer")

        stop_event = threading.Event()
        start = time.monotonic()
        worker._pel_heartbeat_loop(
            message_id="msg-id",
            stop_event=stop_event,
            interval_s=0.02,
            max_duration_s=0.1,
        )
        elapsed = time.monotonic() - start
        assert elapsed < 1.0


class TestProcessAndAckHeartbeat:
    def test_starts_heartbeat_and_joins_after_processing(self, worker, monkeypatch):
        monkeypatch.setattr(worker_main, "INGESTION_PEL_HEARTBEAT_INTERVAL_S", 1)
        events: list = []
        event_lock = threading.Lock()

        def append(item):
            with event_lock:
                events.append(item)

        def fake_heartbeat(message_id, stop_event, interval_s, max_duration_s):
            append(("heartbeat_started", message_id))
            stop_event.wait(timeout=5.0)
            append("heartbeat_stopped")

        def fake_resolve(payload, message_id, fields):
            append(("resolved", message_id))

        monkeypatch.setattr(worker, "_pel_heartbeat_loop", fake_heartbeat)
        monkeypatch.setattr(worker, "_resolve_process_outcome", fake_resolve)
        monkeypatch.setattr(worker, "_decrement_thread_count", lambda: None)

        worker._process_and_ack({}, "msg-abc", {"data": "{}"})

        assert ("heartbeat_started", "msg-abc") in events
        assert ("resolved", "msg-abc") in events
        assert events[-1] == "heartbeat_stopped"

    def test_heartbeat_disabled_when_interval_non_positive(self, worker, monkeypatch):
        monkeypatch.setattr(worker_main, "INGESTION_PEL_HEARTBEAT_INTERVAL_S", 0)
        mock_heartbeat = MagicMock()
        monkeypatch.setattr(worker, "_pel_heartbeat_loop", mock_heartbeat)
        monkeypatch.setattr(worker, "_resolve_process_outcome", lambda p, m, f: None)
        monkeypatch.setattr(worker, "_decrement_thread_count", lambda: None)

        worker._process_and_ack({}, "msg-abc", {"data": "{}"})

        mock_heartbeat.assert_not_called()

    def test_heartbeat_stops_when_processing_raises(self, worker, monkeypatch):
        monkeypatch.setattr(worker_main, "INGESTION_PEL_HEARTBEAT_INTERVAL_S", 1)
        events: list = []
        event_lock = threading.Lock()

        def fake_heartbeat(message_id, stop_event, interval_s, max_duration_s):
            stop_event.wait(timeout=5.0)
            with event_lock:
                events.append("heartbeat_stopped")

        def boom(payload, message_id, fields):
            raise RuntimeError("processing exploded")

        monkeypatch.setattr(worker, "_pel_heartbeat_loop", fake_heartbeat)
        monkeypatch.setattr(worker, "_resolve_process_outcome", boom)
        monkeypatch.setattr(worker, "_decrement_thread_count", lambda: None)

        with pytest.raises(RuntimeError):
            worker._process_and_ack({}, "msg-abc", {"data": "{}"})

        assert events == ["heartbeat_stopped"]


class TestSubprocessProcessGroup:
    def test_popen_uses_new_session(self, worker):
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = MagicMock()
        mock_process.stderr = MagicMock()
        mock_process.poll = MagicMock(side_effect=[None, 0])
        mock_process.stdout.fileno.return_value = 10
        mock_process.stderr.fileno.return_value = 11
        mock_process.stdout.read.return_value = b""
        mock_process.stderr.read.return_value = b""

        with (
            patch("subprocess.Popen", return_value=mock_process) as mock_popen,
            patch("select.select", return_value=([], [], [])),
            patch("fcntl.fcntl"),
        ):
            worker.process_task(_make_payload())

        assert mock_popen.call_args.kwargs.get("start_new_session") is True


class TestKillProcessGroup:
    def test_sigterm_then_sigkill_when_process_ignores_sigterm(self, monkeypatch):
        process = MagicMock()
        process.pid = 12345
        process.poll.return_value = None
        process.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="x", timeout=5),
            None,
        ]

        mock_killpg = MagicMock()
        monkeypatch.setattr(worker_main.os, "killpg", mock_killpg)
        monkeypatch.setattr(worker_main.os, "getpgid", lambda pid: pid)

        worker_main._kill_process_group(process, grace_period_s=0.01)

        assert mock_killpg.call_count == 2
        assert mock_killpg.call_args_list[0].args == (12345, signal.SIGTERM)
        assert mock_killpg.call_args_list[1].args == (12345, signal.SIGKILL)

    def test_no_escalation_when_sigterm_works(self, monkeypatch):
        process = MagicMock()
        process.pid = 12345
        process.poll.return_value = None
        process.wait.return_value = None

        mock_killpg = MagicMock()
        monkeypatch.setattr(worker_main.os, "killpg", mock_killpg)
        monkeypatch.setattr(worker_main.os, "getpgid", lambda pid: pid)

        worker_main._kill_process_group(process, grace_period_s=0.01)

        mock_killpg.assert_called_once_with(12345, signal.SIGTERM)

    def test_returns_early_when_process_already_exited(self, monkeypatch):
        process = MagicMock()
        process.poll.return_value = 0

        mock_killpg = MagicMock()
        monkeypatch.setattr(worker_main.os, "killpg", mock_killpg)

        worker_main._kill_process_group(process)

        mock_killpg.assert_not_called()

    def test_tolerates_process_lookup_error_on_getpgid(self, monkeypatch):
        process = MagicMock()
        process.pid = 12345
        process.poll.return_value = None

        def raise_lookup(pid):
            raise ProcessLookupError()

        mock_killpg = MagicMock()
        monkeypatch.setattr(worker_main.os, "getpgid", raise_lookup)
        monkeypatch.setattr(worker_main.os, "killpg", mock_killpg)

        worker_main._kill_process_group(process)

        mock_killpg.assert_not_called()

    def test_tolerates_process_lookup_error_on_sigterm(self, monkeypatch):
        process = MagicMock()
        process.pid = 12345
        process.poll.return_value = None

        def raise_lookup(pgid, sig):
            raise ProcessLookupError()

        monkeypatch.setattr(worker_main.os, "getpgid", lambda pid: pid)
        monkeypatch.setattr(worker_main.os, "killpg", raise_lookup)

        worker_main._kill_process_group(process)


class TestSubprocessTimeoutKillsProcessGroup:
    def test_timeout_invokes_kill_process_group(self, worker, monkeypatch):
        monkeypatch.setattr(worker_main, "SUBPROCESS_TIMEOUT_S", 1)

        mock_process = MagicMock()
        mock_process.returncode = -9
        mock_process.stdout = MagicMock()
        mock_process.stderr = MagicMock()
        mock_process.stdout.fileno.return_value = 10
        mock_process.stderr.fileno.return_value = 11
        mock_process.stdout.read.return_value = b""
        mock_process.stderr.read.return_value = b""
        mock_process.poll.return_value = None

        time_values = iter([0.0, 0.0, 0.0, 2.0, 2.0, 2.0])
        monkeypatch.setattr(
            worker_main.time,
            "monotonic",
            lambda: next(time_values, 2.0),
        )

        with (
            patch("subprocess.Popen", return_value=mock_process),
            patch("select.select", return_value=([], [], [])),
            patch("fcntl.fcntl"),
            patch.object(worker_main, "_kill_process_group") as mock_kill,
            patch.object(worker, "_update_task_status_to_failed"),
        ):
            outcome = worker.process_task(_make_payload())

        assert outcome == ProcessTaskOutcome.FAIL_FATAL_ACK
        mock_kill.assert_called_once_with(mock_process)

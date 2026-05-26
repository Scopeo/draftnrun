from unittest.mock import MagicMock, patch

import pytest

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

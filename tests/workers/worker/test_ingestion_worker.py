import pytest

from workers.worker import main as worker_main


@pytest.fixture
def worker():
    w = worker_main.Worker.__new__(worker_main.Worker)
    w.stream_name = worker_main.STREAM_NAME
    w.max_concurrent = 1
    w.current_threads = 0
    w.worker_type = "redis_ingestion"
    return w


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

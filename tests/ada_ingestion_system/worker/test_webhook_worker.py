import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

from ada_ingestion_system.worker.base_worker import ProcessTaskOutcome
from ada_ingestion_system.worker.webhook_worker import WebhookWorker, _classify_script_failure


def test_classify_script_failure_fatal_marker():
    outcome = _classify_script_failure("... WEBHOOK_FAILURE_CLASS=fatal error=bad payload ...")
    assert outcome == ProcessTaskOutcome.FAIL_FATAL_ACK


def test_classify_script_failure_defaults_retryable():
    outcome = _classify_script_failure("some random stderr without marker")
    assert outcome == ProcessTaskOutcome.FAIL_RETRY


def test_classify_script_failure_empty_string():
    assert _classify_script_failure("") == ProcessTaskOutcome.FAIL_RETRY


def test_classify_script_failure_partial_marker():
    assert _classify_script_failure("WEBHOOK_FAILURE_CLASS=fata") == ProcessTaskOutcome.FAIL_RETRY


def test_classify_script_failure_both_markers_fatal_wins():
    output = "WEBHOOK_FAILURE_CLASS=fatal something WEBHOOK_FAILURE_CLASS=retry"
    assert _classify_script_failure(output) == ProcessTaskOutcome.FAIL_FATAL_ACK


def _make_worker() -> WebhookWorker:
    """Construct a WebhookWorker without connecting to Redis."""
    with patch("ada_ingestion_system.worker.base_worker._xgroup_create_if_not_exists"):
        return WebhookWorker()


class TestFailRun:
    def test_on_fatal_ack_calls_fail_endpoint(self, monkeypatch):
        """_on_fatal_ack must PATCH the fail endpoint for direct-trigger runs."""
        worker = _make_worker()
        run_id = str(uuid4())
        project_id = str(uuid4())
        fields = {"data": json.dumps({"run_id": run_id, "webhook_id": project_id, "event_id": "evt-1"})}

        monkeypatch.setenv("ADA_URL", "http://test")
        monkeypatch.setenv("WEBHOOK_API_KEY", "key")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("ada_ingestion_system.worker.webhook_worker.httpx.patch", return_value=mock_response) as mock_patch:
            worker._on_fatal_ack("msg-1", fields, reason="422 Unprocessable Entity")

        mock_patch.assert_called_once()
        call_args = mock_patch.call_args
        assert f"/runs/{run_id}/fail" in call_args[0][0]
        body = call_args[1]["json"]
        assert body["error"]["type"] == "FatalError"

    def test_on_dead_letter_calls_fail_endpoint(self, monkeypatch):
        """_on_dead_letter must PATCH the fail endpoint for direct-trigger runs."""
        worker = _make_worker()
        run_id = str(uuid4())
        project_id = str(uuid4())
        fields = {"data": json.dumps({"run_id": run_id, "webhook_id": project_id, "event_id": "evt-2"})}

        monkeypatch.setenv("ADA_URL", "http://test")
        monkeypatch.setenv("WEBHOOK_API_KEY", "key")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("ada_ingestion_system.worker.webhook_worker.httpx.patch", return_value=mock_response) as mock_patch:
            worker._on_dead_letter("msg-2", fields, reason="exceeded max attempts")

        mock_patch.assert_called_once()
        body = mock_patch.call_args[1]["json"]
        assert body["error"]["type"] == "DeadLetter"

    def test_fail_run_skipped_without_run_id(self, monkeypatch):
        """Messages without run_id (provider webhooks) should not call the fail endpoint."""
        worker = _make_worker()
        fields = {"data": json.dumps({"webhook_id": str(uuid4()), "event_id": "evt-3"})}

        monkeypatch.setenv("ADA_URL", "http://test")
        monkeypatch.setenv("WEBHOOK_API_KEY", "key")

        with patch("ada_ingestion_system.worker.webhook_worker.httpx.patch") as mock_patch:
            worker._on_fatal_ack("msg-3", fields, reason="some error")

        mock_patch.assert_not_called()

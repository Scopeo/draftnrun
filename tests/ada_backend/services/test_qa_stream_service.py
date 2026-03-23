import asyncio
import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from ada_backend.database.models import RunStatus
from ada_backend.services.qa.qa_stream_service import (
    QASubscription,
    _is_stream_terminal,
    build_catchup_events,
    build_terminal_event,
    get_validated_qa_session,
    reconstruct_session_replay,
    stream_events,
)

PROJECT_ID = uuid.uuid4()
SESSION_ID = uuid.uuid4()
DATASET_ID = uuid.uuid4()
GRAPH_RUNNER_ID = uuid.uuid4()


def _qa_session(
    *,
    status=RunStatus.PENDING,
    project_id=PROJECT_ID,
    dataset_id=DATASET_ID,
    graph_runner_id=GRAPH_RUNNER_ID,
    total=0,
    passed=0,
    failed=0,
    error=None,
):
    return SimpleNamespace(
        id=SESSION_ID,
        project_id=project_id,
        dataset_id=dataset_id,
        graph_runner_id=graph_runner_id,
        status=status,
        total=total,
        passed=passed,
        failed=failed,
        error=error,
    )


class TestGetValidatedQASession:
    def test_returns_session_when_project_matches(self):
        qa = _qa_session()
        db = MagicMock()
        with patch("ada_backend.services.qa.qa_stream_service.get_qa_session", return_value=qa):
            result = get_validated_qa_session(db, SESSION_ID, PROJECT_ID)
        assert result is qa

    def test_returns_none_when_not_found(self):
        db = MagicMock()
        with patch("ada_backend.services.qa.qa_stream_service.get_qa_session", return_value=None):
            assert get_validated_qa_session(db, SESSION_ID, PROJECT_ID) is None

    def test_returns_none_when_project_mismatch(self):
        qa = _qa_session(project_id=uuid.uuid4())
        db = MagicMock()
        with patch("ada_backend.services.qa.qa_stream_service.get_qa_session", return_value=qa):
            assert get_validated_qa_session(db, SESSION_ID, PROJECT_ID) is None


class TestBuildCatchupEvents:
    def test_pending_session_returns_empty(self):
        qa = _qa_session(status=RunStatus.PENDING)
        assert build_catchup_events(MagicMock(), qa) == []

    def test_no_graph_runner_returns_empty(self):
        qa = _qa_session(status=RunStatus.RUNNING, graph_runner_id=None)
        assert build_catchup_events(MagicMock(), qa) == []

    def test_completed_session_returns_events(self):
        input_id = uuid.uuid4()
        qa = _qa_session(status=RunStatus.COMPLETED)
        with patch(
            "ada_backend.services.qa.qa_stream_service.get_outputs_by_graph_runner",
            return_value=[(input_id, "some output")],
        ):
            events = build_catchup_events(MagicMock(), qa)
        assert len(events) == 1
        parsed = json.loads(events[0])
        assert parsed["type"] == "qa.entry.completed"
        assert parsed["input_id"] == str(input_id)
        assert parsed["success"] is True
        assert parsed["error"] is None

    def test_error_output_flagged(self):
        input_id = uuid.uuid4()
        qa = _qa_session(status=RunStatus.COMPLETED)
        with patch(
            "ada_backend.services.qa.qa_stream_service.get_outputs_by_graph_runner",
            return_value=[(input_id, "Error: something went wrong")],
        ):
            events = build_catchup_events(MagicMock(), qa)
        parsed = json.loads(events[0])
        assert parsed["success"] is False
        assert parsed["error"] == "Error: something went wrong"


class TestBuildTerminalEvent:
    def test_completed_session(self):
        qa = _qa_session(status=RunStatus.COMPLETED, total=10, passed=8, failed=2)
        event = build_terminal_event(qa)
        assert event is not None
        parsed = json.loads(event)
        assert parsed["type"] == "qa.completed"
        assert parsed["summary"]["total"] == 10
        assert parsed["summary"]["passed"] == 8
        assert parsed["summary"]["failed"] == 2
        assert parsed["summary"]["success_rate"] == pytest.approx(80.0)

    def test_completed_zero_total(self):
        qa = _qa_session(status=RunStatus.COMPLETED, total=0, passed=0, failed=0)
        parsed = json.loads(build_terminal_event(qa))
        assert parsed["summary"]["success_rate"] == 0.0

    def test_failed_session(self):
        qa = _qa_session(
            status=RunStatus.FAILED,
            error={"message": "timeout", "type": "TimeoutError"},
        )
        event = build_terminal_event(qa)
        parsed = json.loads(event)
        assert parsed["type"] == "qa.failed"
        assert parsed["error"]["message"] == "timeout"

    def test_failed_session_default_error(self):
        qa = _qa_session(status=RunStatus.FAILED, error=None)
        parsed = json.loads(build_terminal_event(qa))
        assert parsed["error"]["type"] == "UnknownError"

    def test_running_session_returns_none(self):
        qa = _qa_session(status=RunStatus.RUNNING)
        assert build_terminal_event(qa) is None

    def test_pending_session_returns_none(self):
        qa = _qa_session(status=RunStatus.PENDING)
        assert build_terminal_event(qa) is None


class TestReconstructSessionReplay:
    def test_completed_session_returns_catchup_and_terminal(self):
        qa = _qa_session(status=RunStatus.COMPLETED, total=5, passed=5, failed=0)
        input_id = uuid.uuid4()
        db = MagicMock()
        with patch(
            "ada_backend.services.qa.qa_stream_service.get_outputs_by_graph_runner",
            return_value=[(input_id, "ok")],
        ):
            catchup, terminal = reconstruct_session_replay(db, qa)
        assert len(catchup) == 1
        assert terminal is not None
        assert json.loads(terminal)["type"] == "qa.completed"

    def test_pending_session_returns_empty(self):
        qa = _qa_session(status=RunStatus.PENDING)
        catchup, terminal = reconstruct_session_replay(MagicMock(), qa)
        assert catchup == []
        assert terminal is None


class TestIsStreamTerminal:
    def test_qa_completed_is_terminal(self):
        assert _is_stream_terminal(json.dumps({"type": "qa.completed"})) is True

    def test_qa_failed_is_terminal(self):
        assert _is_stream_terminal(json.dumps({"type": "qa.failed"})) is True

    def test_fatal_error_is_terminal(self):
        assert _is_stream_terminal(json.dumps({"type": "error", "fatal": True, "message": "x"})) is True

    def test_non_fatal_error_is_not_terminal(self):
        assert _is_stream_terminal(json.dumps({"type": "error", "message": "x"})) is False

    def test_entry_event_is_not_terminal(self):
        assert _is_stream_terminal(json.dumps({"type": "qa.entry.completed"})) is False

    def test_malformed_json_is_not_terminal(self):
        assert _is_stream_terminal("not json") is False


class TestStreamEvents:
    @pytest.mark.asyncio
    async def test_yields_messages_and_stops_on_terminal(self):
        queue: asyncio.Queue = asyncio.Queue()
        queue.put_nowait(json.dumps({"type": "qa.entry.completed", "input_id": "x"}))
        queue.put_nowait(json.dumps({"type": "qa.completed", "summary": {}}))

        messages = []
        async for msg in stream_events(queue):
            messages.append(json.loads(msg))
        assert len(messages) == 2
        assert messages[-1]["type"] == "qa.completed"

    @pytest.mark.asyncio
    async def test_stops_on_fatal_error(self):
        queue: asyncio.Queue = asyncio.Queue()
        queue.put_nowait(json.dumps({"type": "error", "fatal": True, "message": "Redis unavailable"}))

        messages = []
        async for msg in stream_events(queue):
            messages.append(json.loads(msg))
        assert len(messages) == 1
        assert messages[0]["type"] == "error"
        assert messages[0]["fatal"] is True

    @pytest.mark.asyncio
    async def test_emits_ping_on_timeout(self):
        queue: asyncio.Queue = asyncio.Queue()

        with patch("ada_backend.services.qa.qa_stream_service.PING_TIMEOUT_SECONDS", 0.05):
            got_ping = False

            async def _consume():
                nonlocal got_ping
                async for msg in stream_events(queue):
                    parsed = json.loads(msg)
                    if parsed["type"] == "ping":
                        got_ping = True
                        queue.put_nowait(json.dumps({"type": "qa.completed", "summary": {}}))

            await asyncio.wait_for(_consume(), timeout=2.0)
            assert got_ping


class TestQASubscription:
    def test_stop_sets_event_and_joins(self):
        sub = QASubscription()
        mock_thread = MagicMock()
        sub._thread = mock_thread
        sub.stop()
        assert sub.stop_event.is_set()
        mock_thread.join.assert_called_once_with(timeout=2.0)

    def test_stop_without_thread(self):
        sub = QASubscription()
        sub.stop()
        assert sub.stop_event.is_set()

from unittest.mock import MagicMock
from uuid import uuid4

from ada_backend.services.graph_execution_stream_service import get_running_runs


class TestGetRunningRuns:
    def test_returns_active_events_for_running_runs(self):
        project_id = uuid4()
        run1_id = uuid4()
        run2_id = uuid4()

        mock_run1 = MagicMock()
        mock_run1.id = run1_id
        mock_run2 = MagicMock()
        mock_run2.id = run2_id

        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [mock_run1, mock_run2]

        result = get_running_runs(session, project_id)

        assert len(result) == 2
        assert result[0]["type"] == "run.active"
        assert result[0]["run_id"] == str(run1_id)
        assert result[0]["graph_runner_id"] is None
        assert result[1]["run_id"] == str(run2_id)

    def test_returns_empty_when_no_running_runs(self):
        project_id = uuid4()
        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = []

        result = get_running_runs(session, project_id)
        assert result == []

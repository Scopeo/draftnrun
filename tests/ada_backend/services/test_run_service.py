from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from ada_backend.database.models import CallType, RunStatus
from ada_backend.services.errors import InvalidRunStatusTransition, RunNotFound
from ada_backend.services.run_service import fail_pending_run

MODULE = "ada_backend.services.run_service"


def _make_fake_run(run_id, project_id, status=RunStatus.FAILED):
    run = MagicMock()
    run.id = run_id
    run.project_id = project_id
    run.status = status
    run.trigger = CallType.WEBHOOK
    run.webhook_id = None
    run.integration_trigger_id = None
    run.event_id = None
    run.trace_id = None
    run.result_id = None
    run.error = {"message": "timeout", "type": "DeadLetter"}
    run.started_at = None
    run.finished_at = datetime.now(timezone.utc)
    run.created_at = datetime.now(timezone.utc)
    return run


class TestFailPendingRun:
    def _make_session(self):
        return MagicMock()

    def test_success_transitions_pending_to_failed(self):
        session = self._make_session()
        run_id = uuid4()
        project_id = uuid4()
        error = {"message": "timeout", "type": "DeadLetter"}
        fake_run = _make_fake_run(run_id, project_id)

        with patch(f"{MODULE}.run_repository") as repo:
            repo.fail_run_if_pending.return_value = fake_run
            result = fail_pending_run(session, run_id, error, project_id=project_id)

        repo.fail_run_if_pending.assert_called_once()
        call_kwargs = repo.fail_run_if_pending.call_args
        assert call_kwargs.kwargs.get("project_id") == project_id
        assert result is not None

    def test_success_without_project_id(self):
        session = self._make_session()
        run_id = uuid4()
        project_id = uuid4()
        error = {"message": "timeout", "type": "DeadLetter"}
        fake_run = _make_fake_run(run_id, project_id)

        with patch(f"{MODULE}.run_repository") as repo:
            repo.fail_run_if_pending.return_value = fake_run
            result = fail_pending_run(session, run_id, error)

        call_kwargs = repo.fail_run_if_pending.call_args
        assert call_kwargs.kwargs.get("project_id") is None
        assert result is not None

    def test_raises_run_not_found_when_run_missing(self):
        session = self._make_session()
        run_id = uuid4()

        with patch(f"{MODULE}.run_repository") as repo:
            repo.fail_run_if_pending.return_value = None
            repo.get_run.return_value = None
            with pytest.raises(RunNotFound):
                fail_pending_run(session, run_id, {"message": "err"}, project_id=uuid4())

    def test_raises_run_not_found_when_project_mismatch(self):
        session = self._make_session()
        run_id = uuid4()
        wrong_project_id = uuid4()
        existing_run = MagicMock()
        existing_run.project_id = uuid4()
        existing_run.status = RunStatus.PENDING

        with patch(f"{MODULE}.run_repository") as repo:
            repo.fail_run_if_pending.return_value = None
            repo.get_run.return_value = existing_run
            with pytest.raises(RunNotFound):
                fail_pending_run(session, run_id, {"message": "err"}, project_id=wrong_project_id)

    def test_raises_invalid_transition_when_no_longer_pending(self):
        session = self._make_session()
        run_id = uuid4()
        project_id = uuid4()
        existing_run = MagicMock()
        existing_run.status = RunStatus.RUNNING
        existing_run.project_id = project_id

        with patch(f"{MODULE}.run_repository") as repo:
            repo.fail_run_if_pending.return_value = None
            repo.get_run.return_value = existing_run
            with pytest.raises(InvalidRunStatusTransition) as exc_info:
                fail_pending_run(session, run_id, {"message": "err"}, project_id=project_id)
        assert exc_info.value.current_status == RunStatus.RUNNING.value
        assert exc_info.value.new_status == RunStatus.FAILED.value

    def test_no_unconditional_write_after_status_check(self):
        """Regression: the old code did a read-then-write that could overwrite a concurrent state change."""
        session = self._make_session()
        run_id = uuid4()
        project_id = uuid4()

        with patch(f"{MODULE}.run_repository") as repo:
            repo.fail_run_if_pending.return_value = None
            existing_run = MagicMock()
            existing_run.status = RunStatus.COMPLETED
            existing_run.project_id = project_id
            repo.get_run.return_value = existing_run

            with pytest.raises(InvalidRunStatusTransition):
                fail_pending_run(session, run_id, {"message": "race"}, project_id=project_id)

            repo.update_run_status.assert_not_called()

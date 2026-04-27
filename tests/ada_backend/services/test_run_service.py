from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from ada_backend.database.models import CallType, EnvType, RunStatus
from ada_backend.services.errors import InvalidRunStatusTransition, RunNotFound
from ada_backend.services.run_service import fail_pending_run, retry_run

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
    run.env = None
    run.retry_group_id = None
    run.attempt_number = 1
    run.started_at = None
    run.finished_at = datetime.now(timezone.utc)
    run.created_at = datetime.now(timezone.utc)
    run.updated_at = datetime.now(timezone.utc)
    run.graph_runner_id = None
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


class TestRetryRun:
    def _make_session(self):
        return MagicMock()

    def test_retries_with_persisted_input_and_returns_pending_run(self):
        session = self._make_session()
        run_id = uuid4()
        project_id = uuid4()
        retry_group_id = uuid4()
        new_run_id = uuid4()

        existing_run = MagicMock()
        existing_run.id = run_id
        existing_run.project_id = project_id
        existing_run.retry_group_id = retry_group_id
        existing_run.attempt_number = 1
        existing_run.trigger = CallType.SANDBOX
        existing_run.webhook_id = None
        existing_run.integration_trigger_id = None
        existing_run.event_id = None

        latest_attempt = MagicMock()
        latest_attempt.attempt_number = 1

        created_run = MagicMock()
        created_run.id = new_run_id

        with (
            patch(f"{MODULE}.run_repository") as repo,
            patch(f"{MODULE}.get_run_input", return_value={"messages": [{"role": "user", "content": "retry"}]}),
            patch(f"{MODULE}.create_run", return_value=created_run) as create_run_mock,
            patch(f"{MODULE}.push_run_task", return_value=True) as push_mock,
            patch(f"{MODULE}.setup_tracing_context") as setup_ctx_mock,
        ):
            repo.get_run.return_value = existing_run
            repo.get_latest_run_by_retry_group.return_value = latest_attempt

            result = retry_run(
                session=session,
                run_id=run_id,
                project_id=project_id,
                legacy_env=EnvType.DRAFT,
            )

        assert result.run_id == new_run_id
        create_run_mock.assert_called_once()
        assert create_run_mock.call_args.kwargs["attempt_number"] == 2
        assert create_run_mock.call_args.kwargs["retry_group_id"] == retry_group_id
        push_mock.assert_called_once()
        assert push_mock.call_args.kwargs["input_data"] == {"messages": [{"role": "user", "content": "retry"}]}
        setup_ctx_mock.assert_called_once_with(session=session, project_id=project_id)

    def test_raises_when_no_persisted_input_exists(self):
        session = self._make_session()
        run_id = uuid4()
        project_id = uuid4()
        existing_run = MagicMock()
        existing_run.id = run_id
        existing_run.project_id = project_id
        existing_run.retry_group_id = run_id
        existing_run.attempt_number = 1

        with (
            patch(f"{MODULE}.run_repository") as repo,
            patch(f"{MODULE}.get_run_input", return_value=None),
        ):
            repo.get_run.return_value = existing_run
            with pytest.raises(ValueError, match="Run input not found for retry"):
                retry_run(session=session, run_id=run_id, project_id=project_id, legacy_env=EnvType.PRODUCTION)

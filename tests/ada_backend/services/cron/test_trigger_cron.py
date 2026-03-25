"""Tests for manual cron job trigger functionality."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ada_backend.database.models import CronEntrypoint, CronStatus
from ada_backend.services.cron.errors import CronJobAccessDenied, CronJobNotFound
from ada_backend.services.cron.service import execute_cron_run, trigger_cron_job_now


def _make_cron_job(is_enabled: bool = True, organization_id=None):
    cron_job = MagicMock()
    cron_job.id = uuid4()
    cron_job.organization_id = organization_id or uuid4()
    cron_job.is_enabled = is_enabled
    cron_job.entrypoint = CronEntrypoint.DUMMY_PRINT
    cron_job.payload = {"message": "hello"}
    return cron_job


def _make_cron_run(cron_id):
    run = MagicMock()
    run.id = uuid4()
    run.cron_id = cron_id
    return run


class TestTriggerCronJobNow:
    def test_trigger_enabled_cron_creates_run(self):
        org_id = uuid4()
        cron_job = _make_cron_job(is_enabled=True, organization_id=org_id)
        cron_run = _make_cron_run(cron_job.id)
        session = MagicMock()

        with (
            patch("ada_backend.services.cron.service.get_cron_job", return_value=cron_job),
            patch("ada_backend.services.cron.service.insert_cron_run", return_value=cron_run),
        ):
            response, entrypoint, payload = trigger_cron_job_now(session, cron_job.id, org_id)

        assert response.run_id == cron_run.id
        assert response.cron_id == cron_job.id
        assert entrypoint == cron_job.entrypoint
        assert payload == dict(cron_job.payload)

    def test_trigger_disabled_cron_still_works(self):
        org_id = uuid4()
        cron_job = _make_cron_job(is_enabled=False, organization_id=org_id)
        cron_run = _make_cron_run(cron_job.id)
        session = MagicMock()

        with (
            patch("ada_backend.services.cron.service.get_cron_job", return_value=cron_job),
            patch("ada_backend.services.cron.service.insert_cron_run", return_value=cron_run),
        ):
            response, entrypoint, payload = trigger_cron_job_now(session, cron_job.id, org_id)

        assert response.run_id == cron_run.id
        assert entrypoint == cron_job.entrypoint

    def test_trigger_nonexistent_cron_raises_not_found(self):
        session = MagicMock()

        with (
            patch("ada_backend.services.cron.service.get_cron_job", return_value=None),
            pytest.raises(CronJobNotFound),
        ):
            trigger_cron_job_now(session, uuid4(), uuid4())

    def test_trigger_wrong_org_raises_access_denied(self):
        org_id = uuid4()
        other_org_id = uuid4()
        cron_job = _make_cron_job(is_enabled=True, organization_id=other_org_id)
        session = MagicMock()

        with (
            patch("ada_backend.services.cron.service.get_cron_job", return_value=cron_job),
            pytest.raises(CronJobAccessDenied),
        ):
            trigger_cron_job_now(session, cron_job.id, org_id)

    def test_trigger_creates_run_with_running_status(self):
        org_id = uuid4()
        cron_job = _make_cron_job(is_enabled=True, organization_id=org_id)
        cron_run = _make_cron_run(cron_job.id)
        session = MagicMock()

        with (
            patch("ada_backend.services.cron.service.get_cron_job", return_value=cron_job),
            patch("ada_backend.services.cron.service.insert_cron_run", return_value=cron_run) as mock_insert,
        ):
            trigger_cron_job_now(session, cron_job.id, org_id)

        mock_insert.assert_called_once()
        call_kwargs = mock_insert.call_args.kwargs
        assert call_kwargs["status"] == CronStatus.RUNNING
        assert call_kwargs["cron_id"] == cron_job.id


class TestExecuteCronRun:
    @pytest.mark.asyncio
    async def test_execute_successful_run(self):
        run_id = uuid4()
        cron_id = uuid4()
        payload = {"message": "test"}

        mock_spec = MagicMock()
        mock_spec.execution_payload_model.return_value = MagicMock()
        mock_spec.execution_validator = MagicMock()
        mock_spec.executor = AsyncMock(return_value={"result": "ok"})

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with (
            patch(
                "ada_backend.services.cron.execution.CRON_REGISTRY",
                {CronEntrypoint.DUMMY_PRINT: mock_spec},
            ),
            patch("ada_backend.services.cron.execution.get_db_session", return_value=mock_session),
            patch("ada_backend.services.cron.execution.update_cron_run") as mock_update,
        ):
            await execute_cron_run(run_id, cron_id, CronEntrypoint.DUMMY_PRINT, payload)

        mock_update.assert_called()
        final_call_kwargs = mock_update.call_args_list[-1].kwargs
        assert final_call_kwargs["status"] == CronStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_run_marks_error_on_exception(self):
        run_id = uuid4()
        cron_id = uuid4()
        payload = {"message": "test"}

        mock_spec = MagicMock()
        mock_spec.execution_payload_model.return_value = MagicMock()
        mock_spec.execution_validator = MagicMock()
        mock_spec.executor = AsyncMock(side_effect=RuntimeError("boom"))

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with (
            patch(
                "ada_backend.services.cron.execution.CRON_REGISTRY",
                {CronEntrypoint.DUMMY_PRINT: mock_spec},
            ),
            patch("ada_backend.services.cron.execution.get_db_session", return_value=mock_session),
            patch("ada_backend.services.cron.execution.update_cron_run") as mock_update,
        ):
            await execute_cron_run(run_id, cron_id, CronEntrypoint.DUMMY_PRINT, payload)

        mock_update.assert_called()
        final_call_kwargs = mock_update.call_args_list[-1].kwargs
        assert final_call_kwargs["status"] == CronStatus.ERROR
        assert "boom" in final_call_kwargs["error"]

    @pytest.mark.asyncio
    async def test_execute_invalid_entrypoint_marks_error(self):
        run_id = uuid4()
        cron_id = uuid4()

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with (
            patch("ada_backend.services.cron.execution.CRON_REGISTRY", {}),
            patch("ada_backend.services.cron.execution.get_db_session", return_value=mock_session),
            patch("ada_backend.services.cron.execution.update_cron_run") as mock_update,
        ):
            await execute_cron_run(run_id, cron_id, CronEntrypoint.DUMMY_PRINT, {})

        mock_update.assert_called_once()
        call_kwargs = mock_update.call_args.kwargs
        assert call_kwargs["status"] == CronStatus.ERROR

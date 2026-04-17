from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from ada_backend.database.models import CallType, EnvType, RunStatus
from ada_backend.routers.webhooks.webhook_internal_router import run_project_internal
from ada_backend.schemas.webhook_schema import RunProjectBody


class TestRunProjectInternal:
    @pytest.mark.asyncio
    @patch("ada_backend.routers.webhooks.webhook_internal_router.push_run_task", return_value=True)
    async def test_enqueues_to_run_queue(self, mock_push):
        run_id = uuid4()
        project_id = uuid4()

        response = await run_project_internal(
            project_id=project_id,
            env=EnvType.PRODUCTION,
            body=RunProjectBody(input_data={"text": "hello"}),
            run_id=run_id,
            session=MagicMock(),
            verified_key="webhook",
        )

        assert response == {"status": "accepted", "run_id": str(run_id)}
        mock_push.assert_called_once_with(
            run_id=run_id,
            project_id=project_id,
            env="production",
            input_data={"text": "hello"},
            trigger=CallType.WEBHOOK.value,
            cron_id=None,
            cron_run_id=None,
        )

    @pytest.mark.asyncio
    @patch("ada_backend.routers.webhooks.webhook_internal_router.push_run_task", return_value=True)
    async def test_passes_cron_fields_to_run_queue(self, mock_push):
        run_id = uuid4()
        cron_id = uuid4()
        cron_run_id = uuid4()

        await run_project_internal(
            project_id=uuid4(),
            env=EnvType.PRODUCTION,
            body=RunProjectBody(
                input_data={"text": "hello"},
                cron_id=cron_id,
                cron_run_id=cron_run_id,
            ),
            run_id=run_id,
            session=MagicMock(),
            verified_key="scheduler",
        )

        call_kwargs = mock_push.call_args.kwargs
        assert call_kwargs["cron_id"] == cron_id
        assert call_kwargs["cron_run_id"] == cron_run_id
        assert call_kwargs["trigger"] == CallType.CRON.value

    @pytest.mark.asyncio
    @patch("ada_backend.routers.webhooks.webhook_internal_router.update_run_status")
    @patch("ada_backend.routers.webhooks.webhook_internal_router.push_run_task", return_value=False)
    async def test_marks_run_failed_when_redis_unavailable(self, mock_push, mock_update):
        run_id = uuid4()
        project_id = uuid4()
        session = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await run_project_internal(
                project_id=project_id,
                env=EnvType.PRODUCTION,
                body=RunProjectBody(input_data={"text": "hello"}),
                run_id=run_id,
                session=session,
                verified_key="webhook",
            )

        assert exc_info.value.status_code == 503
        mock_update.assert_called_once()
        assert mock_update.call_args.kwargs["status"] == RunStatus.FAILED

    @pytest.mark.asyncio
    @patch("ada_backend.routers.webhooks.webhook_internal_router.create_run")
    @patch("ada_backend.routers.webhooks.webhook_internal_router.push_run_task", return_value=True)
    async def test_creates_run_when_no_run_id_provided(self, mock_push, mock_create_run):
        new_run_id = uuid4()
        mock_run = MagicMock()
        mock_run.id = new_run_id
        mock_create_run.return_value = mock_run

        response = await run_project_internal(
            project_id=uuid4(),
            env=EnvType.PRODUCTION,
            body=RunProjectBody(input_data={"text": "hello"}),
            run_id=None,
            session=MagicMock(),
            verified_key="webhook",
        )

        mock_create_run.assert_called_once()
        assert response["run_id"] == str(new_run_id)

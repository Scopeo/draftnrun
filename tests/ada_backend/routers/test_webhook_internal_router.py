from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks

from ada_backend.database.models import CallType, EnvType
from ada_backend.routers.webhooks.webhook_internal_router import (
    _execute_cron_run,
    _execute_run,
    run_project_internal,
)
from ada_backend.schemas.webhook_schema import RunProjectBody
from engine.trace.span_context import get_tracing_span


@pytest.fixture(autouse=True)
def reset_tracing_context():
    from engine.trace.span_context import _tracing_context

    token = _tracing_context.set(None)
    yield
    _tracing_context.reset(token)


def _mock_db_context():
    context = MagicMock()
    context.__enter__ = MagicMock(return_value=MagicMock())
    context.__exit__ = MagicMock(return_value=False)
    return context


class TestExecuteRunTracing:
    @pytest.mark.asyncio
    @patch("ada_backend.routers.webhooks.webhook_internal_router.run_env_agent", new_callable=AsyncMock)
    @patch("ada_backend.routers.webhooks.webhook_internal_router.run_with_tracking", new_callable=AsyncMock)
    async def test_sets_cron_id_in_tracing_context(
        self,
        mock_run_with_tracking,
        mock_run_env_agent,
    ):
        captured = {}
        cron_id = uuid4()

        async def fake_run_with_tracking(**kwargs):
            span = get_tracing_span()
            captured["cron_id"] = span.cron_id if span else None
            await kwargs["runner_coro"]
            return None

        mock_run_with_tracking.side_effect = fake_run_with_tracking
        mock_run_env_agent.return_value = MagicMock()

        succeeded, error_msg = await _execute_run(
            run_id=uuid4(),
            project_id=uuid4(),
            env=EnvType.PRODUCTION,
            input_data={"messages": [{"role": "user", "content": "ping"}]},
            trigger=CallType.CRON,
            cron_id=cron_id,
        )

        assert succeeded is True
        assert error_msg is None
        assert captured["cron_id"] == str(cron_id)


class TestExecuteCronRunTracing:
    @pytest.mark.asyncio
    @patch("ada_backend.routers.webhooks.webhook_internal_router._execute_run")
    @patch("ada_backend.routers.webhooks.webhook_internal_router.update_cron_run")
    @patch("ada_backend.routers.webhooks.webhook_internal_router.get_db_session")
    async def test_passes_cron_id_to_execute_run(
        self,
        mock_get_db_session,
        mock_update_cron_run,
        mock_execute_run,
    ):
        mock_get_db_session.return_value = _mock_db_context()
        mock_execute_run.return_value = (True, None)
        cron_id = uuid4()
        cron_run_id = uuid4()

        await _execute_cron_run(
            run_id=uuid4(),
            project_id=uuid4(),
            env=EnvType.PRODUCTION,
            input_data={"messages": [{"role": "user", "content": "ping"}]},
            trigger=CallType.CRON,
            cron_id=cron_id,
            cron_run_id=cron_run_id,
        )

        assert mock_update_cron_run.call_count == 2
        assert mock_execute_run.await_args.kwargs["cron_id"] == cron_id

    @pytest.mark.asyncio
    @patch("ada_backend.routers.webhooks.webhook_internal_router._execute_run")
    @patch("ada_backend.routers.webhooks.webhook_internal_router.update_cron_run")
    @patch("ada_backend.routers.webhooks.webhook_internal_router.get_db_session")
    async def test_does_not_set_cron_id_when_not_provided(
        self,
        mock_get_db_session,
        mock_update_cron_run,
        mock_execute_run,
    ):
        mock_get_db_session.return_value = _mock_db_context()
        mock_execute_run.return_value = (True, None)

        await _execute_cron_run(
            run_id=uuid4(),
            project_id=uuid4(),
            env=EnvType.PRODUCTION,
            input_data={"messages": [{"role": "user", "content": "ping"}]},
            trigger=CallType.CRON,
            cron_id=None,
            cron_run_id=uuid4(),
        )

        assert mock_update_cron_run.call_count == 2
        assert mock_execute_run.await_args.kwargs["cron_id"] is None


class TestRunProjectInternal:
    @pytest.mark.asyncio
    async def test_passes_cron_id_to_background_run_without_cron_run_id(self):
        background_tasks = BackgroundTasks()
        cron_id = uuid4()
        run_id = uuid4()

        response = await run_project_internal(
            project_id=uuid4(),
            env=EnvType.PRODUCTION,
            background_tasks=background_tasks,
            body=RunProjectBody(
                input_data={"messages": [{"role": "user", "content": "ping"}]},
                cron_id=cron_id,
            ),
            run_id=run_id,
            session=MagicMock(),
            verified_key="scheduler",
        )

        assert response == {"status": "accepted", "run_id": str(run_id)}
        assert len(background_tasks.tasks) == 1
        task = background_tasks.tasks[0]
        assert task.func is _execute_run
        assert task.kwargs["cron_id"] == cron_id

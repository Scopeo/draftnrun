from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from ada_backend.database.models import CallType, EnvType
from ada_backend.routers.webhooks.webhook_internal_router import _execute_cron_run
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


class TestExecuteCronRunTracing:
    @pytest.mark.asyncio
    @patch("ada_backend.routers.webhooks.webhook_internal_router._execute_run")
    @patch("ada_backend.routers.webhooks.webhook_internal_router.update_cron_run")
    @patch("ada_backend.routers.webhooks.webhook_internal_router.get_db_session")
    async def test_sets_cron_id_in_tracing_context(
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

        span = get_tracing_span()
        assert span is not None
        assert span.cron_id == str(cron_id)
        assert mock_update_cron_run.call_count == 2

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

        span = get_tracing_span()
        assert span is None
        assert mock_update_cron_run.call_count == 2

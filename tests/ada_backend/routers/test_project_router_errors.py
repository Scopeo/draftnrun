"""Regression tests for project router error handling.

- chat_async must not crash when ProjectEnvironmentBinding.environment is None.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from ada_backend.database.models import EnvType
from ada_backend.routers.project_router import chat_async


def _make_fake_user():
    user = MagicMock()
    user.id = uuid4()
    return user


def _make_binding(environment=None):
    binding = MagicMock()
    binding.environment = environment
    return binding


def _make_run(run_id=None):
    run = MagicMock()
    run.id = run_id or uuid4()
    return run


class TestChatAsyncNoneEnvironment:
    @pytest.mark.asyncio
    @patch("ada_backend.routers.project_router.push_run_task", return_value=True)
    @patch("ada_backend.routers.project_router.create_run")
    @patch("ada_backend.routers.project_router.get_project_env_binding")
    async def test_does_not_crash_when_environment_is_none(
        self, mock_get_binding, mock_create_run, mock_push
    ):
        run = _make_run()
        gr_id = uuid4()
        mock_get_binding.return_value = _make_binding(environment=None)
        mock_create_run.return_value = run

        result = await chat_async(
            project_id=uuid4(),
            graph_runner_id=gr_id,
            user=_make_fake_user(),
            input_data={"messages": [{"role": "user", "content": "hi"}]},
            session=MagicMock(),
        )

        assert result.run_id == run.id
        mock_push.assert_called_once()
        assert mock_push.call_args.kwargs["env"] is None
        assert mock_push.call_args.kwargs["graph_runner_id"] == gr_id

    @pytest.mark.asyncio
    @patch("ada_backend.routers.project_router.push_run_task", return_value=True)
    @patch("ada_backend.routers.project_router.create_run")
    @patch("ada_backend.routers.project_router.get_project_env_binding")
    async def test_passes_env_value_when_environment_is_present(
        self, mock_get_binding, mock_create_run, mock_push
    ):
        mock_env = EnvType.DRAFT
        run = _make_run()
        gr_id = uuid4()
        mock_get_binding.return_value = _make_binding(environment=mock_env)
        mock_create_run.return_value = run

        result = await chat_async(
            project_id=uuid4(),
            graph_runner_id=gr_id,
            user=_make_fake_user(),
            input_data={"messages": [{"role": "user", "content": "hi"}]},
            session=MagicMock(),
        )

        assert result.run_id == run.id
        mock_push.assert_called_once()
        assert mock_push.call_args.kwargs["env"] == mock_env.value
        assert mock_push.call_args.kwargs["graph_runner_id"] == gr_id

    @pytest.mark.asyncio
    @patch("ada_backend.routers.project_router.push_run_task", return_value=False)
    @patch("ada_backend.routers.project_router.update_run_status")
    @patch("ada_backend.routers.project_router.create_run")
    @patch("ada_backend.routers.project_router.get_project_env_binding")
    async def test_returns_503_when_push_fails_with_none_env(
        self, mock_get_binding, mock_create_run, mock_update, mock_push
    ):
        mock_get_binding.return_value = _make_binding(environment=None)
        mock_create_run.return_value = _make_run()

        with pytest.raises(HTTPException) as exc_info:
            await chat_async(
                project_id=uuid4(),
                graph_runner_id=uuid4(),
                user=_make_fake_user(),
                input_data={"messages": [{"role": "user", "content": "hi"}]},
                session=MagicMock(),
            )
        assert exc_info.value.status_code == 503

"""Regression tests for project router error handling.

- chat_async must not crash when ProjectEnvironmentBinding.environment is None.
- LLMProviderError with 429 status_code surfaces as HTTP 429 (not 502).
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from ada_backend.database.models import EnvType
from ada_backend.routers.project_router import (
    chat_async,
    chat_env,
    run_env_agent_endpoint,
)
from engine.components.errors import LLMProviderError


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
    async def test_does_not_crash_when_environment_is_none(self, mock_get_binding, mock_create_run, mock_push):
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
    async def test_passes_env_value_when_environment_is_present(self, mock_get_binding, mock_create_run, mock_push):
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


class TestLLMProviderErrorHttpStatus:
    @pytest.mark.parametrize(
        "provider_code,expected_http,expected_retriable",
        [
            (429, 429, True),
            (500, 502, False),
            (502, 502, False),
            (503, 502, False),
            (504, 502, False),
            (401, 502, False),
            (403, 502, False),
            (400, 502, False),
            (None, 502, False),
        ],
    )
    def test_http_status_and_is_retriable(self, provider_code, expected_http, expected_retriable):
        err = LLMProviderError("test", status_code=provider_code)
        assert err.http_status == expected_http
        assert err.is_retriable == expected_retriable


def _make_verified_api_key():
    key = MagicMock()
    key.organization_id = uuid4()
    key.project_id = uuid4()
    return key


class TestLLMProviderErrorMapping:
    @pytest.mark.asyncio
    @patch("ada_backend.routers.project_router.run_with_tracking")
    @patch("ada_backend.routers.project_router.verify_project_access")
    @patch("ada_backend.routers.project_router.get_db_session")
    async def test_run_env_agent_returns_429_on_rate_limit(self, mock_db_ctx, mock_verify, mock_run_tracking):
        mock_db_ctx.return_value.__enter__ = MagicMock()
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
        mock_run_tracking.side_effect = LLMProviderError(
            "Rate limit exceeded", status_code=429, provider_name="OpenAI"
        )

        with pytest.raises(HTTPException) as exc_info:
            await run_env_agent_endpoint(
                project_id=uuid4(),
                env=EnvType.PRODUCTION,
                input_data={"messages": [{"role": "user", "content": "hi"}]},
                verified_api_key=_make_verified_api_key(),
            )
        assert exc_info.value.status_code == 429
        assert "OpenAI" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("ada_backend.routers.project_router.run_with_tracking")
    @patch("ada_backend.routers.project_router.verify_project_access")
    @patch("ada_backend.routers.project_router.get_db_session")
    async def test_run_env_agent_returns_502_on_server_error(self, mock_db_ctx, mock_verify, mock_run_tracking):
        mock_db_ctx.return_value.__enter__ = MagicMock()
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
        mock_run_tracking.side_effect = LLMProviderError(
            "Internal server error", status_code=500, provider_name="OpenAI"
        )

        with pytest.raises(HTTPException) as exc_info:
            await run_env_agent_endpoint(
                project_id=uuid4(),
                env=EnvType.PRODUCTION,
                input_data={"messages": [{"role": "user", "content": "hi"}]},
                verified_api_key=_make_verified_api_key(),
            )
        assert exc_info.value.status_code == 502

    @pytest.mark.asyncio
    @patch("ada_backend.routers.project_router.run_with_tracking")
    @patch("ada_backend.routers.project_router.verify_project_access")
    @patch("ada_backend.routers.project_router.get_db_session")
    async def test_run_env_agent_returns_502_when_no_status_code(self, mock_db_ctx, mock_verify, mock_run_tracking):
        mock_db_ctx.return_value.__enter__ = MagicMock()
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
        mock_run_tracking.side_effect = LLMProviderError("Connection reset", status_code=None)

        with pytest.raises(HTTPException) as exc_info:
            await run_env_agent_endpoint(
                project_id=uuid4(),
                env=EnvType.PRODUCTION,
                input_data={"messages": [{"role": "user", "content": "hi"}]},
                verified_api_key=_make_verified_api_key(),
            )
        assert exc_info.value.status_code == 502

    @pytest.mark.asyncio
    @patch("ada_backend.routers.project_router.run_with_tracking")
    async def test_chat_env_returns_429_on_rate_limit(self, mock_run_tracking):
        mock_run_tracking.side_effect = LLMProviderError(
            "Rate limit exceeded", status_code=429, provider_name="Anthropic"
        )

        with pytest.raises(HTTPException) as exc_info:
            await chat_env(
                project_id=uuid4(),
                env=EnvType.DRAFT,
                user=_make_fake_user(),
                input_data={"messages": [{"role": "user", "content": "hi"}]},
            )
        assert exc_info.value.status_code == 429
        assert "Anthropic" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("ada_backend.routers.project_router.run_with_tracking")
    async def test_chat_env_returns_502_on_server_error(self, mock_run_tracking):
        mock_run_tracking.side_effect = LLMProviderError(
            "Internal server error", status_code=500, provider_name="OpenAI"
        )

        with pytest.raises(HTTPException) as exc_info:
            await chat_env(
                project_id=uuid4(),
                env=EnvType.DRAFT,
                user=_make_fake_user(),
                input_data={"messages": [{"role": "user", "content": "hi"}]},
            )
        assert exc_info.value.status_code == 502

    @pytest.mark.asyncio
    @patch("ada_backend.routers.project_router.run_with_tracking")
    async def test_chat_env_returns_502_when_no_status_code(self, mock_run_tracking):
        mock_run_tracking.side_effect = LLMProviderError("Connection reset", status_code=None)

        with pytest.raises(HTTPException) as exc_info:
            await chat_env(
                project_id=uuid4(),
                env=EnvType.DRAFT,
                user=_make_fake_user(),
                input_data={"messages": [{"role": "user", "content": "hi"}]},
            )
        assert exc_info.value.status_code == 502

"""Regression tests for graph router error handling.

- IntegrityError on bind_graph_to_env must return 409 (Sentry issue 107482131).
- ValueError handlers must return custom messages, never str(e) (Sentry issue 105517762).
- No Python exception strings may leak into HTTP responses.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import DBAPIError, IntegrityError

from ada_backend.database.models import EnvType
from ada_backend.routers.graph_router import (
    bind_graph_to_env,
    deploy_graph,
    get_project_graph,
    load_copy_graph_runner,
    load_version_as_draft,
    save_graph_version,
)
from ada_backend.services.errors import (
    GraphNotBoundToProjectError,
    GraphNotFound,
    GraphRunnerAlreadyInEnvironmentError,
    GraphVersionSavingFromNonDraftError,
)


def _make_fake_user():
    user = MagicMock()
    user.id = uuid4()
    return user


class TestBindGraphToEnvIntegrityError:
    @patch(
        "ada_backend.routers.graph_router.bind_graph_to_env_service",
        side_effect=IntegrityError("stmt", {}, Exception("duplicate key")),
    )
    def test_returns_409_on_concurrent_bind(self, _mock_service):
        session = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            bind_graph_to_env(
                project_id=uuid4(),
                graph_runner_id=uuid4(),
                env=EnvType.PRODUCTION,
                user=_make_fake_user(),
                session=session,
            )
        assert exc_info.value.status_code == 409
        assert "concurrently bound" in exc_info.value.detail
        session.rollback.assert_called_once()


def _make_fake_project(organization_id=None):
    project = MagicMock()
    project.organization_id = organization_id or uuid4()
    return project


INTERNAL_ERROR_MSG = "Parameter 'tools' not found in component definitions for component 'abc-123'"


class TestValueErrorNeverLeaksPythonMessage:
    """ValueError handlers must return a custom message, never str(e)."""

    @patch("ada_backend.routers.graph_router.save_graph_version_service", side_effect=ValueError(INTERNAL_ERROR_MSG))
    @patch("ada_backend.routers.graph_router.get_project", return_value=_make_fake_project())
    def test_save_graph_version(self, _mock_project, _mock_service):
        with pytest.raises(HTTPException) as exc_info:
            save_graph_version(uuid4(), uuid4(), _make_fake_user(), MagicMock())
        assert exc_info.value.status_code == 400
        assert INTERNAL_ERROR_MSG not in exc_info.value.detail
        assert "could not be cloned" in exc_info.value.detail

    @patch("ada_backend.routers.graph_router.deploy_graph_service", side_effect=ValueError(INTERNAL_ERROR_MSG))
    @patch("ada_backend.routers.graph_router.get_project", return_value=_make_fake_project())
    def test_deploy_graph(self, _mock_project, _mock_service):
        with pytest.raises(HTTPException) as exc_info:
            deploy_graph(uuid4(), uuid4(), _make_fake_user(), MagicMock())
        assert exc_info.value.status_code == 400
        assert INTERNAL_ERROR_MSG not in exc_info.value.detail
        assert "could not be cloned" in exc_info.value.detail

    @patch("ada_backend.routers.graph_router.load_copy_graph_service", side_effect=ValueError(INTERNAL_ERROR_MSG))
    @patch("ada_backend.routers.graph_router.get_project", return_value=_make_fake_project())
    def test_load_copy_graph(self, _mock_project, _mock_service):
        with pytest.raises(HTTPException) as exc_info:
            load_copy_graph_runner(uuid4(), uuid4(), _make_fake_user(), MagicMock())
        assert exc_info.value.status_code == 400
        assert INTERNAL_ERROR_MSG not in exc_info.value.detail
        assert "could not be cloned" in exc_info.value.detail

    @patch(
        "ada_backend.routers.graph_router.load_version_as_draft_service", side_effect=ValueError(INTERNAL_ERROR_MSG)
    )
    def test_load_version_as_draft(self, _mock_service):
        with pytest.raises(HTTPException) as exc_info:
            load_version_as_draft(uuid4(), uuid4(), _make_fake_user(), MagicMock())
        assert exc_info.value.status_code == 400
        assert INTERNAL_ERROR_MSG not in exc_info.value.detail
        assert "could not be cloned" in exc_info.value.detail

    @patch("ada_backend.routers.graph_router.get_graph_service", side_effect=ValueError(INTERNAL_ERROR_MSG))
    def test_get_project_graph(self, _mock_service):
        with pytest.raises(HTTPException) as exc_info:
            get_project_graph(uuid4(), uuid4(), _make_fake_user(), MagicMock())
        assert exc_info.value.status_code == 400
        assert INTERNAL_ERROR_MSG not in exc_info.value.detail
        assert "corrupted or incomplete" in exc_info.value.detail


class TestDomainExceptionsUseCustomMessages:
    """ServiceError subclasses should carry the caller-facing message used by the global handler."""

    @patch("ada_backend.routers.graph_router.save_graph_version_service", side_effect=GraphNotFound(uuid4()))
    @patch("ada_backend.routers.graph_router.get_project", return_value=_make_fake_project())
    def test_graph_not_found(self, _mock_project, _mock_service):
        runner_id = uuid4()
        with pytest.raises(GraphNotFound) as exc_info:
            save_graph_version(uuid4(), runner_id, _make_fake_user(), MagicMock())
        assert exc_info.value.status_code == 404
        assert str(exc_info.value.graph_id) in exc_info.value.detail
        assert "not found" in exc_info.value.detail.lower()

    @patch(
        "ada_backend.routers.graph_router.save_graph_version_service",
        side_effect=GraphNotBoundToProjectError(uuid4()),
    )
    @patch("ada_backend.routers.graph_router.get_project", return_value=_make_fake_project())
    def test_graph_not_bound(self, _mock_project, _mock_service):
        with pytest.raises(GraphNotBoundToProjectError) as exc_info:
            save_graph_version(uuid4(), uuid4(), _make_fake_user(), MagicMock())
        assert exc_info.value.status_code == 403
        assert str(exc_info.value.graph_runner_id) in exc_info.value.detail
        assert "not bound" in exc_info.value.detail.lower()

    @patch(
        "ada_backend.routers.graph_router.save_graph_version_service",
        side_effect=GraphVersionSavingFromNonDraftError(uuid4(), "production"),
    )
    @patch("ada_backend.routers.graph_router.get_project", return_value=_make_fake_project())
    def test_save_from_non_draft(self, _mock_project, _mock_service):
        with pytest.raises(GraphVersionSavingFromNonDraftError) as exc_info:
            save_graph_version(uuid4(), uuid4(), _make_fake_user(), MagicMock())
        assert exc_info.value.status_code == 400
        assert "draft" in exc_info.value.detail.lower()

    @patch(
        "ada_backend.routers.graph_router.deploy_graph_service",
        side_effect=GraphRunnerAlreadyInEnvironmentError(uuid4(), "production"),
    )
    @patch("ada_backend.routers.graph_router.get_project", return_value=_make_fake_project())
    def test_already_in_environment(self, _mock_project, _mock_service):
        with pytest.raises(GraphRunnerAlreadyInEnvironmentError) as exc_info:
            deploy_graph(uuid4(), uuid4(), _make_fake_user(), MagicMock())
        assert exc_info.value.status_code == 400
        assert str(exc_info.value.graph_runner_id) in exc_info.value.detail
        assert "already in production" in exc_info.value.detail.lower()

    @patch(
        "ada_backend.routers.graph_router.save_graph_version_service",
        side_effect=DBAPIError("SELECT 1", {}, Exception("TCP connection reset by peer (10.0.3.42:5432)")),
    )
    @patch("ada_backend.routers.graph_router.get_project", return_value=_make_fake_project())
    def test_connection_error_no_leak(self, _mock_project, _mock_service):
        with pytest.raises(HTTPException) as exc_info:
            save_graph_version(uuid4(), uuid4(), _make_fake_user(), MagicMock())
        assert exc_info.value.status_code == 503
        assert "TCP" not in exc_info.value.detail
        assert "10.0.3.42" not in exc_info.value.detail
        assert "Database connection failed" in exc_info.value.detail


class TestDeployGraphIntegrityError:
    @patch(
        "ada_backend.routers.graph_router.deploy_graph_service",
        side_effect=IntegrityError("stmt", {}, Exception("duplicate key")),
    )
    @patch("ada_backend.routers.graph_router.get_project", return_value=_make_fake_project())
    def test_returns_409_on_concurrent_deploy(self, _mock_project, _mock_service):
        session = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            deploy_graph(uuid4(), uuid4(), _make_fake_user(), session)
        assert exc_info.value.status_code == 409
        assert "another deployment" in exc_info.value.detail.lower()
        session.rollback.assert_called_once()


class TestUnexpectedExceptionsBubbleToGlobalHandler:
    """Routers should let unexpected exceptions bubble to the global Exception handler."""

    @patch(
        "ada_backend.routers.graph_router.save_graph_version_service",
        side_effect=RuntimeError("segfault in C extension"),
    )
    @patch("ada_backend.routers.graph_router.get_project", return_value=_make_fake_project())
    def test_save_version_catch_all(self, _mock_project, _mock_service):
        with pytest.raises(RuntimeError, match="segfault in C extension"):
            save_graph_version(uuid4(), uuid4(), _make_fake_user(), MagicMock())

"""
Tests for save_graph_version_service - testing version saving logic and error cases.

NOTE: These tests require PostgreSQL due to regex constraints in the GraphRunner model.
When the test suite is migrated to PostgreSQL, these tests will work automatically.
For now, they are marked as integration tests.
"""

import uuid

import pytest
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.services.errors import GraphNotBoundToProjectError, GraphNotFound, GraphVersionSavingFromNonDraftError
from ada_backend.services.graph.deploy_graph_service import save_graph_version_service

# Mark all tests in this module as integration tests requiring PostgreSQL
pytestmark = pytest.mark.skip(
    reason="Tests require PostgreSQL (SQLite doesn't support regex constraints). "
    "Run with PostgreSQL test database or enable when test suite is migrated to PostgreSQL."
)


@pytest.fixture
def test_organization():
    """Create a test organization."""
    return uuid.uuid4()


@pytest.fixture
def test_project(ada_backend_mock_session: Session, test_organization):
    """Create a test project."""
    project_id = uuid.uuid4()
    project = db.WorkflowProject(
        id=project_id,
        name="Test Project",
        description="Test project for save version",
        organization_id=test_organization,
        type=db.ProjectType.WORKFLOW,
    )
    ada_backend_mock_session.add(project)
    ada_backend_mock_session.commit()
    return project


@pytest.fixture
def draft_graph_runner(ada_backend_mock_session: Session, test_project):
    """
    Create a draft graph runner (env='draft', tag_version=null).
    This is the only version that can be saved.
    """
    graph_runner_id = uuid.uuid4()
    graph_runner = db.GraphRunner(
        id=graph_runner_id,
        tag_version=None,
    )
    ada_backend_mock_session.add(graph_runner)
    ada_backend_mock_session.flush()

    binding = db.ProjectEnvironmentBinding(
        project_id=test_project.id,
        graph_runner_id=graph_runner_id,
        environment=db.EnvType.DRAFT,
    )
    ada_backend_mock_session.add(binding)
    ada_backend_mock_session.commit()

    return graph_runner


class TestSaveVersionService:
    """Tests for save_graph_version_service."""

    def test_saves_version_from_draft(
        self,
        ada_backend_mock_session: Session,
        test_project,
        draft_graph_runner,
    ):
        """Test that saving a version from draft works correctly."""
        result = save_graph_version_service(
            session=ada_backend_mock_session,
            graph_runner_id=draft_graph_runner.id,
            project_id=test_project.id,
        )

        assert result.project_id == test_project.id
        assert result.draft_graph_runner_id == draft_graph_runner.id
        assert result.saved_graph_runner_id != draft_graph_runner.id
        assert result.tag_version == "0.0.1"

        # Verify the saved graph runner exists and has the correct tag
        saved_graph = (
            ada_backend_mock_session.query(db.GraphRunner)
            .filter(db.GraphRunner.id == result.saved_graph_runner_id)
            .first()
        )
        assert saved_graph is not None
        assert saved_graph.tag_version == "0.0.1"

        # Verify the saved graph runner is bound to the project with no environment
        saved_binding = (
            ada_backend_mock_session.query(db.ProjectEnvironmentBinding)
            .filter(db.ProjectEnvironmentBinding.graph_runner_id == result.saved_graph_runner_id)
            .first()
        )
        assert saved_binding is not None
        assert saved_binding.project_id == test_project.id
        assert saved_binding.environment is None

        # Verify draft still exists
        draft_binding = (
            ada_backend_mock_session.query(db.ProjectEnvironmentBinding)
            .filter(
                db.ProjectEnvironmentBinding.graph_runner_id == draft_graph_runner.id,
                db.ProjectEnvironmentBinding.environment == db.EnvType.DRAFT,
            )
            .first()
        )
        assert draft_binding is not None

    def test_saves_multiple_versions_increments_tag(
        self,
        ada_backend_mock_session: Session,
        test_project,
        draft_graph_runner,
    ):
        """Test that saving multiple versions increments the tag version correctly."""
        # First save
        result1 = save_graph_version_service(
            session=ada_backend_mock_session,
            graph_runner_id=draft_graph_runner.id,
            project_id=test_project.id,
        )
        assert result1.tag_version == "0.0.1"

        # Second save
        result2 = save_graph_version_service(
            session=ada_backend_mock_session,
            graph_runner_id=draft_graph_runner.id,
            project_id=test_project.id,
        )
        assert result2.tag_version == "0.0.2"

        # Third save
        result3 = save_graph_version_service(
            session=ada_backend_mock_session,
            graph_runner_id=draft_graph_runner.id,
            project_id=test_project.id,
        )
        assert result3.tag_version == "0.0.3"

        # Verify all saved versions exist
        saved_ids = [result1.saved_graph_runner_id, result2.saved_graph_runner_id, result3.saved_graph_runner_id]
        saved_graphs = ada_backend_mock_session.query(db.GraphRunner).filter(db.GraphRunner.id.in_(saved_ids)).all()
        assert len(saved_graphs) == 3

    def test_raises_error_when_graph_not_found(
        self,
        ada_backend_mock_session: Session,
        test_project,
    ):
        """Test that saving a version from a non-existent graph raises an error."""
        non_existent_id = uuid.uuid4()

        with pytest.raises(GraphNotFound) as exc_info:
            save_graph_version_service(
                session=ada_backend_mock_session,
                graph_runner_id=non_existent_id,
                project_id=test_project.id,
            )

        assert str(non_existent_id) in str(exc_info.value)

    def test_raises_error_when_graph_not_bound_to_project(
        self,
        ada_backend_mock_session: Session,
        test_project,
    ):
        """Test that saving a version from a graph not bound to project raises an error."""
        graph_runner_id = uuid.uuid4()
        graph_runner = db.GraphRunner(
            id=graph_runner_id,
            tag_version=None,
        )
        ada_backend_mock_session.add(graph_runner)
        ada_backend_mock_session.commit()

        with pytest.raises(GraphNotBoundToProjectError) as exc_info:
            save_graph_version_service(
                session=ada_backend_mock_session,
                graph_runner_id=graph_runner_id,
                project_id=test_project.id,
            )

        assert str(graph_runner_id) in str(exc_info.value)

    def test_raises_error_when_saving_from_production(
        self,
        ada_backend_mock_session: Session,
        test_project,
    ):
        """Test that saving a version from production raises an error."""
        # Create a production graph runner
        graph_runner_id = uuid.uuid4()
        graph_runner = db.GraphRunner(
            id=graph_runner_id,
            tag_version="1.0.0",
        )
        ada_backend_mock_session.add(graph_runner)
        ada_backend_mock_session.flush()

        binding = db.ProjectEnvironmentBinding(
            project_id=test_project.id,
            graph_runner_id=graph_runner_id,
            environment=db.EnvType.PRODUCTION,
        )
        ada_backend_mock_session.add(binding)
        ada_backend_mock_session.commit()

        with pytest.raises(GraphVersionSavingFromNonDraftError) as exc_info:
            save_graph_version_service(
                session=ada_backend_mock_session,
                graph_runner_id=graph_runner_id,
                project_id=test_project.id,
            )

        error_message = str(exc_info.value)
        assert "can only save versions from draft" in error_message.lower()
        assert "production" in error_message.lower()
        assert str(graph_runner_id) in error_message

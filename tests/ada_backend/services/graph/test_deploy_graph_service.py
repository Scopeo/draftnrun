"""
Tests for deploy_graph_service - specifically testing save_graph_version_service.
Tests ensure that versions can be saved from draft graph runners with proper validation.
"""

import uuid
import pytest
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.services.graph.deploy_graph_service import save_graph_version_service
from ada_backend.repositories.env_repository import get_env_relationship_by_graph_runner_id
from ada_backend.services.errors import (
    GraphVersionSavingFromNonDraftError,
    GraphNotFound,
    GraphNotBoundToProjectError,
)


@pytest.fixture
def test_organization(ada_backend_mock_session: Session):
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
    This is the only type that can be saved as a version.
    """
    graph_runner_id = uuid.uuid4()
    graph_runner = db.GraphRunner(
        id=graph_runner_id,
        tag_version=None,  # Draft has no tag
    )
    ada_backend_mock_session.add(graph_runner)
    ada_backend_mock_session.flush()

    # Bind to project with DRAFT environment
    binding = db.ProjectEnvironmentBinding(
        project_id=test_project.id,
        graph_runner_id=graph_runner_id,
        environment=db.EnvType.DRAFT,
    )
    ada_backend_mock_session.add(binding)
    ada_backend_mock_session.commit()

    return graph_runner


@pytest.fixture
def production_graph_runner(ada_backend_mock_session: Session, test_project):
    """
    Create a production graph runner (env='production', tag_version='v1.0.0').
    This should not be allowed to be saved as a version.
    """
    graph_runner_id = uuid.uuid4()
    graph_runner = db.GraphRunner(
        id=graph_runner_id,
        tag_version="1.0.0",  # Production has a tag
    )
    ada_backend_mock_session.add(graph_runner)
    ada_backend_mock_session.flush()

    # Bind to project with PRODUCTION environment
    binding = db.ProjectEnvironmentBinding(
        project_id=test_project.id,
        graph_runner_id=graph_runner_id,
        environment=db.EnvType.PRODUCTION,
    )
    ada_backend_mock_session.add(binding)
    ada_backend_mock_session.commit()

    return graph_runner


class TestSaveGraphVersionService:
    """
    Tests for the save_graph_version_service function.
    """

    def test_successfully_saves_version_from_draft(
        self, ada_backend_mock_session: Session, test_project, draft_graph_runner
    ):
        """
        Test that a version can be successfully saved from a draft graph runner.
        """
        result = save_graph_version_service(
            session=ada_backend_mock_session,
            graph_runner_id=draft_graph_runner.id,
            project_id=test_project.id,
        )

        # Verify response structure
        assert result.project_id == test_project.id
        assert result.draft_graph_runner_id == draft_graph_runner.id
        assert result.saved_graph_runner_id != draft_graph_runner.id  # Should be a new ID
        assert result.tag_version is not None
        assert result.tag_version == "0.0.1"  # First version should be 0.0.1

        # Verify the saved graph runner exists and has correct properties
        saved_graph_runner = (
            ada_backend_mock_session.query(db.GraphRunner)
            .filter(db.GraphRunner.id == result.saved_graph_runner_id)
            .first()
        )
        assert saved_graph_runner is not None
        assert saved_graph_runner.tag_version == result.tag_version

        # Verify the saved graph runner is bound with environment=None
        saved_binding = get_env_relationship_by_graph_runner_id(ada_backend_mock_session, result.saved_graph_runner_id)
        assert saved_binding.environment is None
        assert saved_binding.project_id == test_project.id

        # Verify the draft graph runner is still intact
        draft_binding = get_env_relationship_by_graph_runner_id(ada_backend_mock_session, draft_graph_runner.id)
        assert draft_binding.environment == db.EnvType.DRAFT
        assert draft_graph_runner.tag_version is None  # Draft should still have no tag

    def test_raises_error_for_nonexistent_graph_runner(self, ada_backend_mock_session: Session, test_project):
        """
        Test that appropriate error is raised for non-existent graph runner.
        """
        non_existent_id = uuid.uuid4()

        with pytest.raises(GraphNotFound) as exc_info:
            save_graph_version_service(
                session=ada_backend_mock_session,
                graph_runner_id=non_existent_id,
                project_id=test_project.id,
            )

        assert exc_info.value.graph_id == non_existent_id
        assert "not found" in str(exc_info.value).lower()

    def test_raises_error_for_unbound_graph_runner(self, ada_backend_mock_session: Session, test_project):
        """
        Test that error is raised when graph runner is not bound to any project.
        """
        # Create a graph runner but don't bind it to a project
        unbound_graph_runner_id = uuid.uuid4()
        graph_runner = db.GraphRunner(id=unbound_graph_runner_id, tag_version=None)
        ada_backend_mock_session.add(graph_runner)
        ada_backend_mock_session.commit()

        with pytest.raises(GraphNotBoundToProjectError) as exc_info:
            save_graph_version_service(
                session=ada_backend_mock_session,
                graph_runner_id=unbound_graph_runner_id,
                project_id=test_project.id,
            )

        assert exc_info.value.graph_runner_id == unbound_graph_runner_id
        assert exc_info.value.bound_project_id is None
        assert "not bound" in str(exc_info.value).lower()

    def test_raises_error_for_production_graph_runner(
        self, ada_backend_mock_session: Session, test_project, production_graph_runner
    ):
        """
        Test that saving a version from a production graph runner is rejected.
        """
        with pytest.raises(GraphVersionSavingFromNonDraftError) as exc_info:
            save_graph_version_service(
                session=ada_backend_mock_session,
                graph_runner_id=production_graph_runner.id,
                project_id=test_project.id,
            )

        assert exc_info.value.graph_runner_id == production_graph_runner.id
        assert exc_info.value.current_environment == "production"
        assert "can only save versions from draft" in str(exc_info.value).lower()
        assert "production" in str(exc_info.value).lower()

    def test_version_tag_increments_correctly(
        self, ada_backend_mock_session: Session, test_project, draft_graph_runner
    ):
        """
        Test that version tags increment correctly when saving multiple versions.
        """
        # Save first version
        result1 = save_graph_version_service(
            session=ada_backend_mock_session,
            graph_runner_id=draft_graph_runner.id,
            project_id=test_project.id,
        )
        assert result1.tag_version == "0.0.1"

        # Save second version
        result2 = save_graph_version_service(
            session=ada_backend_mock_session,
            graph_runner_id=draft_graph_runner.id,
            project_id=test_project.id,
        )
        assert result2.tag_version == "0.0.2"

        # Save third version
        result3 = save_graph_version_service(
            session=ada_backend_mock_session,
            graph_runner_id=draft_graph_runner.id,
            project_id=test_project.id,
        )
        assert result3.tag_version == "0.0.3"

        # Verify all saved graph runners have different IDs
        assert result1.saved_graph_runner_id != result2.saved_graph_runner_id
        assert result2.saved_graph_runner_id != result3.saved_graph_runner_id
        assert result1.saved_graph_runner_id != result3.saved_graph_runner_id

    def test_response_includes_both_graph_runner_ids(
        self, ada_backend_mock_session: Session, test_project, draft_graph_runner
    ):
        """
        Test that the response includes both the draft graph runner ID and the saved graph runner ID.
        """
        result = save_graph_version_service(
            session=ada_backend_mock_session,
            graph_runner_id=draft_graph_runner.id,
            project_id=test_project.id,
        )

        # Verify both IDs are present and correct
        assert result.draft_graph_runner_id == draft_graph_runner.id
        assert result.saved_graph_runner_id is not None
        assert result.saved_graph_runner_id != draft_graph_runner.id

    def test_saved_version_has_none_environment(
        self, ada_backend_mock_session: Session, test_project, draft_graph_runner
    ):
        """
        Test that the saved version is bound with environment=None.
        """
        result = save_graph_version_service(
            session=ada_backend_mock_session,
            graph_runner_id=draft_graph_runner.id,
            project_id=test_project.id,
        )

        # Verify the saved graph runner has environment=None
        saved_binding = (
            ada_backend_mock_session.query(db.ProjectEnvironmentBinding)
            .filter(db.ProjectEnvironmentBinding.graph_runner_id == result.saved_graph_runner_id)
            .first()
        )
        assert saved_binding is not None
        assert saved_binding.environment is None
        assert saved_binding.project_id == test_project.id

import uuid
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.setup_db import get_db_session
from ada_backend.services.errors import GraphNotBoundToProjectError, GraphNotFound, GraphVersionSavingFromNonDraftError
from ada_backend.services.graph.deploy_graph_service import save_graph_version_service
from ada_backend.services.project_service import delete_project_service


def create_test_project(
    session: Session,
    project_id: UUID,
    name: str,
    description: str,
    organization_id: UUID,
) -> db.WorkflowProject:
    """
    Helper function to create a test project with the given parameters.

    Args:
        session: Database session
        project_id: UUID for the project
        name: Project name
        description: Project description
        organization_id: UUID for the organization

    Returns:
        The created WorkflowProject instance
    """
    project = db.WorkflowProject(
        id=project_id,
        name=name,
        description=description,
        organization_id=organization_id,
        type=db.ProjectType.WORKFLOW,
    )
    session.add(project)
    session.commit()
    return project


class TestSaveVersionService:
    """Tests for save_graph_version_service."""

    def test_saves_version_from_draft(self):
        """Test that saving a version from draft works correctly."""
        with get_db_session() as session:
            # Create test organization and project
            test_organization = uuid.uuid4()
            project_id = uuid.uuid4()
            create_test_project(
                session=session,
                project_id=project_id,
                name="Test Project",
                description="Test project for save version",
                organization_id=test_organization,
            )

            # Create draft graph runner
            graph_runner_id = uuid.uuid4()
            graph_runner = db.GraphRunner(
                id=graph_runner_id,
                tag_version=None,
            )
            session.add(graph_runner)
            session.flush()

            binding = db.ProjectEnvironmentBinding(
                project_id=project_id,
                graph_runner_id=graph_runner_id,
                environment=db.EnvType.DRAFT,
            )
            session.add(binding)
            session.commit()

            # Test saving version
            result = save_graph_version_service(
                session=session,
                graph_runner_id=graph_runner_id,
                project_id=project_id,
            )

            assert result.project_id == project_id
            assert result.draft_graph_runner_id == graph_runner_id
            assert result.saved_graph_runner_id != graph_runner_id
            assert result.tag_version == "0.0.1"

            # Verify the saved graph runner exists and has the correct tag
            saved_graph = (
                session.query(db.GraphRunner).filter(db.GraphRunner.id == result.saved_graph_runner_id).first()
            )
            assert saved_graph is not None
            assert saved_graph.tag_version == "0.0.1"

            # Verify the saved graph runner is bound to the project with no environment
            saved_binding = (
                session.query(db.ProjectEnvironmentBinding)
                .filter(db.ProjectEnvironmentBinding.graph_runner_id == result.saved_graph_runner_id)
                .first()
            )
            assert saved_binding is not None
            assert saved_binding.project_id == project_id
            assert saved_binding.environment is None

            # Verify draft still exists
            draft_binding = (
                session.query(db.ProjectEnvironmentBinding)
                .filter(
                    db.ProjectEnvironmentBinding.graph_runner_id == graph_runner_id,
                    db.ProjectEnvironmentBinding.environment == db.EnvType.DRAFT,
                )
                .first()
            )
            assert draft_binding is not None

            # Cleanup
            delete_project_service(session, project_id)

    def test_saves_multiple_versions_increments_tag(self):
        """Test that saving multiple versions increments the tag version correctly."""
        with get_db_session() as session:
            # Create test organization and project
            test_organization = uuid.uuid4()
            project_id = uuid.uuid4()
            create_test_project(
                session=session,
                project_id=project_id,
                name="Test Project",
                description="Test project for save version",
                organization_id=test_organization,
            )

            # Create draft graph runner
            graph_runner_id = uuid.uuid4()
            graph_runner = db.GraphRunner(
                id=graph_runner_id,
                tag_version=None,
            )
            session.add(graph_runner)
            session.flush()

            binding = db.ProjectEnvironmentBinding(
                project_id=project_id,
                graph_runner_id=graph_runner_id,
                environment=db.EnvType.DRAFT,
            )
            session.add(binding)
            session.commit()

            # First save
            result1 = save_graph_version_service(
                session=session,
                graph_runner_id=graph_runner_id,
                project_id=project_id,
            )
            assert result1.tag_version == "0.0.1"

            # Second save
            result2 = save_graph_version_service(
                session=session,
                graph_runner_id=graph_runner_id,
                project_id=project_id,
            )
            assert result2.tag_version == "0.0.2"

            # Third save
            result3 = save_graph_version_service(
                session=session,
                graph_runner_id=graph_runner_id,
                project_id=project_id,
            )
            assert result3.tag_version == "0.0.3"

            # Verify all saved versions exist
            saved_ids = [result1.saved_graph_runner_id, result2.saved_graph_runner_id, result3.saved_graph_runner_id]
            saved_graphs = session.query(db.GraphRunner).filter(db.GraphRunner.id.in_(saved_ids)).all()
            assert len(saved_graphs) == 3

            # Cleanup
            delete_project_service(session, project_id)

    def test_raises_error_when_graph_not_found(self):
        """Test that saving a version from a non-existent graph raises an error."""
        with get_db_session() as session:
            # Create test organization and project
            test_organization = uuid.uuid4()
            project_id = uuid.uuid4()
            create_test_project(
                session=session,
                project_id=project_id,
                name="Test Project",
                description="Test project for save version",
                organization_id=test_organization,
            )

            non_existent_id = uuid.uuid4()

            with pytest.raises(GraphNotFound) as exc_info:
                save_graph_version_service(
                    session=session,
                    graph_runner_id=non_existent_id,
                    project_id=project_id,
                )

            assert str(non_existent_id) in str(exc_info.value)

            # Cleanup
            delete_project_service(session, project_id)

    def test_raises_error_when_graph_not_bound_to_project(self):
        """Test that saving a version from a graph not bound to project raises an error."""
        with get_db_session() as session:
            # Create test organization and project
            test_organization = uuid.uuid4()
            project_id = uuid.uuid4()
            create_test_project(
                session=session,
                project_id=project_id,
                name="Test Project",
                description="Test project for save version",
                organization_id=test_organization,
            )

            # Create graph runner but don't bind it to the project
            graph_runner_id = uuid.uuid4()
            graph_runner = db.GraphRunner(
                id=graph_runner_id,
                tag_version=None,
            )
            session.add(graph_runner)
            session.commit()

            with pytest.raises(GraphNotBoundToProjectError) as exc_info:
                save_graph_version_service(
                    session=session,
                    graph_runner_id=graph_runner_id,
                    project_id=project_id,
                )

            assert str(graph_runner_id) in str(exc_info.value)

            # Cleanup
            delete_project_service(session, project_id)

    def test_raises_error_when_saving_from_production(self):
        """Test that saving a version from production raises an error."""
        with get_db_session() as session:
            # Create test organization and project
            test_organization = uuid.uuid4()
            project_id = uuid.uuid4()
            create_test_project(
                session=session,
                project_id=project_id,
                name="Test Project",
                description="Test project for save version",
                organization_id=test_organization,
            )

            # Create a production graph runner
            graph_runner_id = uuid.uuid4()
            graph_runner = db.GraphRunner(
                id=graph_runner_id,
                tag_version="1.0.0",
            )
            session.add(graph_runner)
            session.flush()

            binding = db.ProjectEnvironmentBinding(
                project_id=project_id,
                graph_runner_id=graph_runner_id,
                environment=db.EnvType.PRODUCTION,
            )
            session.add(binding)
            session.commit()

            with pytest.raises(GraphVersionSavingFromNonDraftError) as exc_info:
                save_graph_version_service(
                    session=session,
                    graph_runner_id=graph_runner_id,
                    project_id=project_id,
                )

            error_message = str(exc_info.value)
            assert "can only save versions from draft" in error_message.lower()
            assert "production" in error_message.lower()
            assert str(graph_runner_id) in error_message

            # Cleanup
            delete_project_service(session, project_id)

    def test_raises_error_when_graph_bound_to_different_project(self):
        """Test that saving a version with wrong project_id raises an error."""
        with get_db_session() as session:
            test_organization = uuid.uuid4()
            correct_project_id = uuid.uuid4()
            create_test_project(
                session=session,
                project_id=correct_project_id,
                name="Test Project",
                description="Test project",
                organization_id=test_organization,
            )

            graph_runner_id = uuid.uuid4()
            graph_runner = db.GraphRunner(id=graph_runner_id, tag_version=None)
            session.add(graph_runner)
            session.flush()

            binding = db.ProjectEnvironmentBinding(
                project_id=correct_project_id,
                graph_runner_id=graph_runner_id,
                environment=db.EnvType.DRAFT,
            )
            session.add(binding)
            session.commit()

            wrong_project_id = uuid.uuid4()
            with pytest.raises(GraphNotBoundToProjectError) as exc_info:
                save_graph_version_service(
                    session=session,
                    graph_runner_id=graph_runner_id,
                    project_id=wrong_project_id,
                )

            error_message = str(exc_info.value)
            assert str(graph_runner_id) in error_message
            assert str(wrong_project_id) in error_message
            assert str(correct_project_id) in error_message

            # Cleanup
            delete_project_service(session, correct_project_id)

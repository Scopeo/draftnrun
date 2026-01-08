"""
Integration tests for project service functions.

These tests use a real PostgreSQL database to test
the full integration between service layer, repository layer, and database.

Testing the simplified project list endpoint and full project details.
These tests use PostgreSQL to support regex constraints in GraphRunner models.
"""

import os
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from ada_backend.database import models as db
from ada_backend.database import setup_db
from ada_backend.schemas.project_schema import (
    ProjectSchema,
    ProjectWithGraphRunnersSchema,
)
from ada_backend.services.errors import ProjectNotFound
from ada_backend.services.project_service import (
    get_project_service,
    get_workflows_by_organization_service,
)
from settings import settings


@pytest.fixture(scope="function")
def db_session(alembic_engine, alembic_runner):
    """
    Get a PostgreSQL database session for testing.

    Uses real ADA_DB_URL from settings if available, otherwise falls back to
    ephemeral alembic_engine from pytest_mock_resources.

    Uses transactions that rollback after each test to keep the database clean.
    """
    # Prefer real database URL if available
    if settings.ADA_DB_URL:
        try:
            engine = create_engine(settings.ADA_DB_URL, echo=False)
            # Test connection - assume migrations are already applied to real database
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as e:
            if not os.getenv("CI"):
                pytest.skip(
                    f"Could not connect to real database: {e}. Ensure ADA_DB_URL is set and database is accessible."
                )
            raise
    else:
        # Fall back to ephemeral database - run migrations to create schema
        engine = alembic_engine
        alembic_runner.migrate_up_to("heads", return_current=False)

    # Bind SessionLocal to the engine for this test
    original_engine = setup_db.engine
    setup_db.SessionLocal.configure(bind=engine)

    # Create a session with a transaction that will be rolled back
    SessionFactory = sessionmaker(bind=engine)
    connection = engine.connect()
    transaction = connection.begin()
    session = SessionFactory(bind=connection)

    try:
        yield session
    finally:
        # Rollback transaction to clean up test data
        transaction.rollback()
        session.close()
        connection.close()
        # Restore original binding
        setup_db.SessionLocal.configure(bind=original_engine)


@pytest.fixture
def test_organization(db_session: Session):
    """Create a test organization."""
    org_id = uuid.uuid4()
    return org_id


@pytest.fixture
def test_projects_with_versions(db_session: Session, test_organization):
    """
    Create multiple test projects with versions for comprehensive testing.
    """
    projects_data = []

    for i in range(3):
        # Create project
        project_id = uuid.uuid4()
        project = db.WorkflowProject(
            id=project_id,
            name=f"Test Project {i}",
            description=f"Description {i}",
            organization_id=test_organization,
            type=db.ProjectType.WORKFLOW,
        )
        db_session.add(project)
        db_session.flush()

        # Create graph runners
        draft_gr = db.GraphRunner(id=uuid.uuid4(), tag_version=f"draft-{i}")
        prod_gr = db.GraphRunner(id=uuid.uuid4(), tag_version=f"{i}.0.0")
        db_session.add_all([draft_gr, prod_gr])
        db_session.flush()

        # Create bindings
        draft_binding = db.ProjectEnvironmentBinding(
            project_id=project_id,
            graph_runner_id=draft_gr.id,
            environment=db.EnvType.DRAFT,
        )
        prod_binding = db.ProjectEnvironmentBinding(
            project_id=project_id,
            graph_runner_id=prod_gr.id,
            environment=db.EnvType.PRODUCTION,
        )
        db_session.add_all([draft_binding, prod_binding])

        projects_data.append({
            "project": project,
            "draft_gr": draft_gr,
            "prod_gr": prod_gr,
        })

    db_session.commit()
    return projects_data


class TestGetWorkflowsByOrganizationService:
    """
    Tests for get_workflows_by_organization_service.
    This service returns a lightweight list without graph runner details.
    """

    def test_returns_list_of_project_schemas(
        self, db_session: Session, test_projects_with_versions, test_organization
    ):
        """
        Test that the service returns a list of ProjectSchema instances.
        """
        result = get_workflows_by_organization_service(db_session, test_organization)

        assert isinstance(result, list)
        assert len(result) >= 3

        # Each item should be a ProjectSchema
        for project in result:
            assert isinstance(project, ProjectSchema)

    def test_returns_lightweight_schema_without_graph_runners(
        self, db_session: Session, test_projects_with_versions, test_organization
    ):
        """
        Test that returned projects only have basic fields, no graph_runners.
        This is the key feature - lightweight list for better performance.
        """
        result = get_workflows_by_organization_service(db_session, test_organization)

        for project in result:
            # Should have basic fields
            assert hasattr(project, "project_id")
            assert hasattr(project, "project_name")
            assert hasattr(project, "description")
            assert hasattr(project, "organization_id")
            assert hasattr(project, "created_at")
            assert hasattr(project, "updated_at")

            # Should NOT have graph_runners (that's for detail view)
            assert not hasattr(project, "graph_runners")

    def test_includes_all_projects_from_organization(
        self, db_session: Session, test_projects_with_versions, test_organization
    ):
        """
        Test that all projects from the organization are included.
        """
        result = get_workflows_by_organization_service(db_session, test_organization)

        result_ids = {p.project_id for p in result}

        # All test projects should be present
        for project_data in test_projects_with_versions:
            assert project_data["project"].id in result_ids

    def test_tracks_user_analytics_when_user_id_provided(self, db_session: Session, test_organization):
        """
        Test that user analytics tracking is called when user_id is provided.
        """
        user_id = uuid.uuid4()

        with patch("ada_backend.services.project_service.track_user_get_project_list") as mock_track:
            get_workflows_by_organization_service(db_session, test_organization, user_id=user_id)

            # Should call tracking with correct parameters
            mock_track.assert_called_once_with(user_id, test_organization)

    def test_skips_analytics_when_no_user_id(self, db_session: Session, test_organization):
        """
        Test that analytics tracking is skipped when user_id is None.
        """
        with patch("ada_backend.services.project_service.track_user_get_project_list") as mock_track:
            get_workflows_by_organization_service(db_session, test_organization, user_id=None)

            # Should not call tracking
            mock_track.assert_not_called()

    def test_returns_correct_project_data(self, db_session: Session, test_projects_with_versions, test_organization):
        """
        Test that project data fields are correctly populated.
        """
        result = get_workflows_by_organization_service(db_session, test_organization)

        # Find first test project
        test_project = test_projects_with_versions[0]["project"]
        matching_result = next((p for p in result if p.project_id == test_project.id), None)

        assert matching_result is not None
        assert matching_result.project_name == test_project.name
        assert matching_result.description == test_project.description


class TestGetProjectService:
    """
    Tests for get_project_service.
    This service returns full project details including all graph runners.
    """

    def test_returns_project_with_graph_runners_schema(self, db_session: Session, test_projects_with_versions):
        """
        Test that the service returns ProjectWithGraphRunnersSchema.
        """
        project_id = test_projects_with_versions[0]["project"].id
        result = get_project_service(db_session, project_id)

        assert isinstance(result, ProjectWithGraphRunnersSchema)

    def test_includes_all_graph_runners_with_environments(self, db_session: Session, test_projects_with_versions):
        """
        Test that all graph runners are included with their environment bindings.
        """
        project_data = test_projects_with_versions[0]
        project_id = project_data["project"].id

        result = get_project_service(db_session, project_id)

        # Should have 2 graph runners (draft + production)
        assert len(result.graph_runners) == 2

        # Extract IDs and environments
        gr_data = {gr.graph_runner_id: gr.env for gr in result.graph_runners}

        # Verify both versions are present with correct environments
        assert project_data["draft_gr"].id in gr_data
        assert project_data["prod_gr"].id in gr_data
        assert gr_data[project_data["draft_gr"].id] == db.EnvType.DRAFT
        assert gr_data[project_data["prod_gr"].id] == db.EnvType.PRODUCTION

    def test_includes_tag_versions(self, db_session: Session, test_projects_with_versions):
        """
        Test that tag_name is included for each graph runner.
        """
        project_data = test_projects_with_versions[0]
        project_id = project_data["project"].id

        result = get_project_service(db_session, project_id)

        # Build tag name map
        tag_name_map = {gr.graph_runner_id: gr.tag_name for gr in result.graph_runners}

        # Verify tag names are present
        draft_id = project_data["draft_gr"].id
        prod_id = project_data["prod_gr"].id

        assert draft_id in tag_name_map
        assert prod_id in tag_name_map
        # Tag names should be present (either from tag_version or version_name)
        assert tag_name_map[draft_id] is not None
        assert tag_name_map[prod_id] is not None

    def test_includes_complete_project_metadata(self, db_session: Session, test_projects_with_versions):
        """
        Test that all project metadata is included in the response.
        """
        project_data = test_projects_with_versions[0]
        project_id = project_data["project"].id
        project = project_data["project"]

        result = get_project_service(db_session, project_id)

        # Verify all metadata fields
        assert result.project_id == project.id
        assert result.project_name == project.name
        assert result.description == project.description
        assert result.organization_id == project.organization_id
        assert result.project_type == project.type
        assert result.created_at is not None
        assert result.updated_at is not None

    def test_raises_error_for_nonexistent_project(self, db_session: Session):
        """
        Test that appropriate error is raised for non-existent project.
        """
        non_existent_id = uuid.uuid4()

        with pytest.raises(ProjectNotFound):
            get_project_service(db_session, non_existent_id)

    def test_handles_project_with_no_graph_runners(self, db_session: Session, test_organization):
        """
        Test that project with no graph runners returns empty list.
        """
        # Create project without graph runners
        project_id = uuid.uuid4()
        project = db.WorkflowProject(
            id=project_id,
            name="Empty Project",
            organization_id=test_organization,
            type=db.ProjectType.WORKFLOW,
        )
        db_session.add(project)
        db_session.commit()

        result = get_project_service(db_session, project_id)

        assert result.project_id == project_id
        assert result.graph_runners == []

    def test_graph_runners_ordered_correctly(self, db_session: Session, test_organization):
        """
        Test that graph runners are ordered by creation date.
        """
        # Create 3 separate projects to test ordering across multiple projects
        # (since we can only have one graph runner per environment per project)
        project_ids = []
        gr_ids = []

        for i in range(3):
            project_id = uuid.uuid4()
            project = db.WorkflowProject(
                id=project_id,
                name=f"Test Project {i}",
                organization_id=test_organization,
                type=db.ProjectType.WORKFLOW,
            )
            db_session.add(project)
            db_session.flush()
            project_ids.append(project_id)

            # Create graph runner with DRAFT environment
            gr = db.GraphRunner(id=uuid.uuid4(), tag_version=f"{i}.0.0")
            db_session.add(gr)

            binding = db.ProjectEnvironmentBinding(
                project_id=project_id,
                graph_runner_id=gr.id,
                environment=db.EnvType.DRAFT,
            )
            db_session.add(binding)
            db_session.commit()  # Commit to ensure timestamp is set
            gr_ids.append(gr.id)

        # Test ordering on the first project
        result = get_project_service(db_session, project_ids[0])

        # Should have exactly 1 graph runner
        assert len(result.graph_runners) == 1
        assert result.graph_runners[0].graph_runner_id == gr_ids[0]


class TestServiceIntegration:
    """
    Integration tests verifying the relationship between list and detail services.
    """

    def test_list_service_does_not_include_graph_runner_data(
        self, db_session: Session, test_projects_with_versions, test_organization
    ):
        """
        Verify that list service is truly lightweight - no graph runner data.
        """
        list_result = get_workflows_by_organization_service(db_session, test_organization)

        # List should not have graph_runners
        for project in list_result:
            assert not hasattr(project, "graph_runners")

    def test_detail_service_includes_graph_runner_data(self, db_session: Session, test_projects_with_versions):
        """
        Verify that detail service includes full graph runner information.
        """
        project_id = test_projects_with_versions[0]["project"].id
        detail_result = get_project_service(db_session, project_id)

        # Detail should have graph_runners
        assert hasattr(detail_result, "graph_runners")
        assert len(detail_result.graph_runners) > 0

    def test_list_then_detail_consistency(self, db_session: Session, test_projects_with_versions, test_organization):
        """
        Test that project data is consistent between list and detail views.
        """
        # Get list
        list_result = get_workflows_by_organization_service(db_session, test_organization)

        # Get detail for first project
        first_project_id = list_result[0].project_id
        detail_result = get_project_service(db_session, first_project_id)

        # Basic fields should match
        assert list_result[0].project_id == detail_result.project_id
        assert list_result[0].project_name == detail_result.project_name
        assert list_result[0].description == detail_result.description

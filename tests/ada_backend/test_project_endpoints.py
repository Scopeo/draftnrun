"""
Integration tests for project service functions (converted from endpoint tests).

These tests use a real PostgreSQL database to test
the full integration between service layer, repository layer, and database.

Testing project CRUD operations via service functions.
These tests use PostgreSQL to support regex constraints in GraphRunner models.
"""

import os
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from ada_backend.database import setup_db
from ada_backend.database.seed.utils import COMPONENT_UUIDS
from ada_backend.schemas.project_schema import (
    ProjectCreateSchema,
    ProjectUpdateSchema,
)
from ada_backend.services.errors import ProjectNotFound
from ada_backend.services.graph.get_graph_service import get_graph_service
from ada_backend.services.project_service import (
    create_workflow,
    delete_project_service,
    get_project_service,
    get_workflows_by_organization_service,
    update_project_service,
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
        transaction.rollback()
        session.close()
        connection.close()
        setup_db.SessionLocal.configure(bind=original_engine)


@pytest.fixture
def test_organization():
    """Create a test organization ID."""
    return uuid.uuid4()


@pytest.fixture
def test_user_id():
    """Create a test user ID."""
    return uuid.uuid4()


def test_create_project(db_session: Session, test_organization, test_user_id):
    """Test creating a project via service."""
    project_id = uuid.uuid4()
    project_schema = ProjectCreateSchema(
        project_id=project_id,
        project_name=f"test project {project_id}",
        description="test project description",
    )

    with patch("ada_backend.services.project_service.track_project_created") as mock_track:
        result = create_workflow(
            session=db_session,
            user_id=test_user_id,
            organization_id=test_organization,
            project_schema=project_schema,
        )

        # Verify tracking was called
        mock_track.assert_called_once_with(test_user_id, test_organization, project_id, project_schema.project_name)

    # Verify project was created
    assert isinstance(result, dict) or hasattr(result, "project_id")
    assert result.project_id == project_id
    assert result.project_name == f"test project {project_id}"
    assert result.description == "test project description"
    assert result.organization_id == test_organization
    assert result.created_at is not None
    assert result.updated_at is not None
    assert len(result.graph_runners) > 0


def test_get_project_by_organization(db_session: Session, test_organization, test_user_id):
    """Test getting projects by organization via service."""
    # Create multiple projects first
    project_ids = []
    for i in range(3):
        project_id = uuid.uuid4()
        project_schema = ProjectCreateSchema(
            project_id=project_id,
            project_name=f"test project {i}",
            description=f"Description {i}",
        )
        create_workflow(
            session=db_session,
            user_id=test_user_id,
            organization_id=test_organization,
            project_schema=project_schema,
        )
        project_ids.append(project_id)

    # Get projects by organization
    result = get_workflows_by_organization_service(db_session, test_organization)

    assert isinstance(result, list)
    assert len(result) > 0
    assert all(hasattr(project, "project_id") for project in result)
    assert all(hasattr(project, "project_name") for project in result)
    assert all(hasattr(project, "description") for project in result)
    assert all(hasattr(project, "organization_id") for project in result)
    assert all(project.organization_id == test_organization for project in result)

    # Verify created projects are present
    result_ids = {p.project_id for p in result}
    for project_id in project_ids:
        assert project_id in result_ids


def test_get_project(db_session: Session, test_organization, test_user_id):
    """Test getting a single project via service."""
    # Create a project
    project_id = uuid.uuid4()
    project_schema = ProjectCreateSchema(
        project_id=project_id,
        project_name=f"test project {project_id}",
        description="test project description",
    )
    create_workflow(
        session=db_session,
        user_id=test_user_id,
        organization_id=test_organization,
        project_schema=project_schema,
    )

    # Get the project
    result = get_project_service(db_session, project_id)

    assert isinstance(result, dict) or hasattr(result, "project_id")
    assert result.project_id == project_id
    assert result.project_name == f"test project {project_id}"
    assert result.description == "test project description"
    assert result.organization_id == test_organization
    assert result.created_at is not None
    assert result.updated_at is not None
    assert len(result.graph_runners) > 0


def test_check_project_has_input_component(db_session: Session, test_organization, test_user_id):
    """Test that created project has a graph runner with start component."""
    # Create a project
    project_id = uuid.uuid4()
    project_schema = ProjectCreateSchema(
        project_id=project_id,
        project_name=f"test project {project_id}",
        description="test project description",
    )
    create_workflow(
        session=db_session,
        user_id=test_user_id,
        organization_id=test_organization,
        project_schema=project_schema,
    )

    # Get the project
    project = get_project_service(db_session, project_id)
    assert len(project.graph_runners) > 0

    # Get the draft graph runner
    graph_runner_id = project.graph_runners[0].graph_runner_id

    # Get the graph details
    graph = get_graph_service(
        session=db_session,
        project_id=project_id,
        graph_runner_id=graph_runner_id,
    )

    assert len(graph.component_instances) > 0
    assert graph.component_instances[0].component_id == str(COMPONENT_UUIDS["start"])


def test_update_project(db_session: Session, test_organization, test_user_id):
    """Test updating a project via service."""
    # Create a project
    project_id = uuid.uuid4()
    project_schema = ProjectCreateSchema(
        project_id=project_id,
        project_name=f"test project {project_id}",
        description="test project description",
    )
    create_workflow(
        session=db_session,
        user_id=test_user_id,
        organization_id=test_organization,
        project_schema=project_schema,
    )

    # Update the project
    update_schema = ProjectUpdateSchema(
        project_name=f"updated test project {project_id}",
        description="updated test project description",
    )

    with patch("ada_backend.services.project_service.track_project_saved") as mock_track:
        result = update_project_service(
            session=db_session,
            user_id=test_user_id,
            project_id=project_id,
            project_schema=update_schema,
        )

        # Verify tracking was called
        mock_track.assert_called_once_with(test_user_id, project_id)

    assert isinstance(result, dict) or hasattr(result, "project_id")
    assert result.project_id == project_id
    assert result.project_name == f"updated test project {project_id}"
    assert result.description == "updated test project description"


def test_delete_project(db_session: Session, test_organization, test_user_id):
    """Test deleting a project via service."""
    # Create a project
    project_id = uuid.uuid4()
    project_schema = ProjectCreateSchema(
        project_id=project_id,
        project_name=f"test project {project_id}",
        description="test project description",
    )
    create_workflow(
        session=db_session,
        user_id=test_user_id,
        organization_id=test_organization,
        project_schema=project_schema,
    )

    # Get graph runner IDs before deletion
    project = get_project_service(db_session, project_id)
    graph_runner_ids = [gr.graph_runner_id for gr in project.graph_runners]

    # Delete the project
    result = delete_project_service(db_session, project_id)

    assert isinstance(result, dict) or hasattr(result, "project_id")
    assert "project_id" in result.__dict__ or result.project_id == project_id
    assert result.project_id == project_id
    assert "graph_runner_ids" in result.__dict__
    assert isinstance(result.graph_runner_ids, list)
    assert len(result.graph_runner_ids) > 0
    assert set(result.graph_runner_ids) == set(graph_runner_ids)

    # Verify that the project has been deleted
    with pytest.raises(ProjectNotFound):
        get_project_service(db_session, project_id)

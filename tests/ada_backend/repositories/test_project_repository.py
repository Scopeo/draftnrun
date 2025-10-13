"""
Tests for project repository functions.
Testing the versioning features and graph runner management.
"""
import uuid
import pytest
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.repositories.project_repository import (
    get_project_with_details,
    get_workflows_by_organization,
)
from ada_backend.schemas.project_schema import ProjectWithGraphRunnersSchema
from ada_backend.database.setup_db import get_db


@pytest.fixture
def db_session():
    """Get a database session for testing."""
    session_gen = get_db()
    session = next(session_gen)
    yield session
    session.close()


@pytest.fixture
def test_organization(db_session: Session):
    """Create a test organization."""
    org_id = uuid.uuid4()
    return org_id


@pytest.fixture
def test_workflow_with_versions(db_session: Session, test_organization):
    """
    Create a test workflow project with multiple graph runner versions.
    """
    # Create workflow project
    project_id = uuid.uuid4()
    project = db.WorkflowProject(
        id=project_id,
        name="Test Workflow",
        description="Test workflow for versioning",
        organization_id=test_organization,
        type=db.ProjectType.WORKFLOW,
    )
    db_session.add(project)
    db_session.flush()

    # Create multiple graph runners (versions)
    draft_graph_runner = db.GraphRunner(
        id=uuid.uuid4(),
        tag_version="draft-v1",
    )
    production_graph_runner = db.GraphRunner(
        id=uuid.uuid4(),
        tag_version="v1.0.0",
    )
    db_session.add_all([draft_graph_runner, production_graph_runner])
    db_session.flush()

    # Create environment bindings
    draft_binding = db.ProjectEnvironmentBinding(
        project_id=project_id,
        graph_runner_id=draft_graph_runner.id,
        environment=db.EnvType.DRAFT,
    )
    production_binding = db.ProjectEnvironmentBinding(
        project_id=project_id,
        graph_runner_id=production_graph_runner.id,
        environment=db.EnvType.PRODUCTION,
    )
    db_session.add_all([draft_binding, production_binding])
    db_session.commit()

    return {
        "project": project,
        "draft_graph_runner": draft_graph_runner,
        "production_graph_runner": production_graph_runner,
    }


class TestGetProjectWithDetails:
    """Tests for get_project_with_details function."""

    def test_returns_correct_schema(
        self, db_session: Session, test_workflow_with_versions
    ):
        """
        Test that get_project_with_details returns ProjectWithGraphRunnersSchema.
        """
        project_id = test_workflow_with_versions["project"].id
        result = get_project_with_details(db_session, project_id)

        assert isinstance(result, ProjectWithGraphRunnersSchema)
        assert result.project_id == project_id
        assert result.project_name == "Test Workflow"
        assert result.description == "Test workflow for versioning"

    def test_includes_all_graph_runners(
        self, db_session: Session, test_workflow_with_versions
    ):
        """
        Test that all graph runners for the project are included.
        """
        project_id = test_workflow_with_versions["project"].id
        result = get_project_with_details(db_session, project_id)

        assert len(result.graph_runners) == 2

        # Extract graph runner IDs
        gr_ids = [gr.graph_runner_id for gr in result.graph_runners]

        # Both versions should be present
        assert test_workflow_with_versions["draft_graph_runner"].id in gr_ids
        assert test_workflow_with_versions["production_graph_runner"].id in gr_ids

    def test_graph_runners_have_correct_environments(
        self, db_session: Session, test_workflow_with_versions
    ):
        """
        Test that each graph runner has the correct environment binding.
        """
        project_id = test_workflow_with_versions["project"].id
        result = get_project_with_details(db_session, project_id)

        # Build a map of graph_runner_id -> env
        env_map = {gr.graph_runner_id: gr.env for gr in result.graph_runners}

        draft_id = test_workflow_with_versions["draft_graph_runner"].id
        prod_id = test_workflow_with_versions["production_graph_runner"].id

        assert env_map[draft_id] == db.EnvType.DRAFT
        assert env_map[prod_id] == db.EnvType.PRODUCTION

    def test_graph_runners_have_correct_tag_versions(
        self, db_session: Session, test_workflow_with_versions
    ):
        """
        Test that tag_version is correctly included for each graph runner.
        """
        project_id = test_workflow_with_versions["project"].id
        result = get_project_with_details(db_session, project_id)

        # Build a map of graph_runner_id -> tag_version
        version_map = {gr.graph_runner_id: gr.tag_version for gr in result.graph_runners}

        draft_id = test_workflow_with_versions["draft_graph_runner"].id
        prod_id = test_workflow_with_versions["production_graph_runner"].id

        assert version_map[draft_id] == "draft-v1"
        assert version_map[prod_id] == "v1.0.0"

    def test_graph_runners_ordered_by_creation_date(
        self, db_session: Session, test_organization
    ):
        """
        Test that graph runners are ordered by their creation date.
        """
        # Create project
        project_id = uuid.uuid4()
        project = db.WorkflowProject(
            id=project_id,
            name="Test Project",
            organization_id=test_organization,
            type=db.ProjectType.WORKFLOW,
        )
        db_session.add(project)
        db_session.flush()

        # Create graph runners with deliberate ordering
        gr1 = db.GraphRunner(id=uuid.uuid4(), tag_version="v1")
        db_session.add(gr1)
        db_session.flush()

        gr2 = db.GraphRunner(id=uuid.uuid4(), tag_version="v2")
        db_session.add(gr2)
        db_session.flush()

        gr3 = db.GraphRunner(id=uuid.uuid4(), tag_version="v3")
        db_session.add(gr3)
        db_session.flush()

        # Create bindings
        for gr in [gr1, gr2, gr3]:
            binding = db.ProjectEnvironmentBinding(
                project_id=project_id,
                graph_runner_id=gr.id,
                environment=db.EnvType.DRAFT,
            )
            db_session.add(binding)

        db_session.commit()

        result = get_project_with_details(db_session, project_id)

        # Graph runners should be in order of creation
        gr_ids = [gr.graph_runner_id for gr in result.graph_runners]
        assert gr_ids == [gr1.id, gr2.id, gr3.id]

    def test_handles_project_not_found(self, db_session: Session):
        """
        Test that ValueError is raised when project doesn't exist.
        """
        non_existent_id = uuid.uuid4()

        with pytest.raises(ValueError, match=f"Project {non_existent_id} not found"):
            get_project_with_details(db_session, non_existent_id)

    def test_handles_project_with_no_graph_runners(
        self, db_session: Session, test_organization
    ):
        """
        Test that a project with no graph runners returns empty list.
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

        result = get_project_with_details(db_session, project_id)

        assert result.project_id == project_id
        assert result.graph_runners == []

    def test_includes_project_metadata(
        self, db_session: Session, test_workflow_with_versions
    ):
        """
        Test that all project metadata fields are included.
        """
        project_id = test_workflow_with_versions["project"].id
        result = get_project_with_details(db_session, project_id)

        # Check all fields are present
        assert result.project_id is not None
        assert result.project_name is not None
        assert result.project_type == db.ProjectType.WORKFLOW
        assert result.description is not None
        assert result.organization_id is not None
        assert result.created_at is not None
        assert result.updated_at is not None


class TestGetWorkflowsByOrganization:
    """Tests for get_workflows_by_organization function."""

    def test_returns_all_workflows_for_organization(
        self, db_session: Session, test_organization
    ):
        """
        Test that all workflows for an organization are returned.
        """
        # Create multiple workflow projects
        workflow1_id = uuid.uuid4()
        workflow1 = db.WorkflowProject(
            id=workflow1_id,
            name="Workflow 1",
            organization_id=test_organization,
            type=db.ProjectType.WORKFLOW,
        )

        workflow2_id = uuid.uuid4()
        workflow2 = db.WorkflowProject(
            id=workflow2_id,
            name="Workflow 2",
            organization_id=test_organization,
            type=db.ProjectType.WORKFLOW,
        )

        db_session.add_all([workflow1, workflow2])
        db_session.commit()

        results = get_workflows_by_organization(db_session, test_organization)

        assert len(results) >= 2
        workflow_ids = [w.id for w in results]
        assert workflow1_id in workflow_ids
        assert workflow2_id in workflow_ids

    def test_filters_by_organization(
        self, db_session: Session, test_organization
    ):
        """
        Test that only workflows from the specified organization are returned.
        """
        # Create workflow in test organization
        test_workflow_id = uuid.uuid4()
        test_workflow = db.WorkflowProject(
            id=test_workflow_id,
            name="Test Workflow",
            organization_id=test_organization,
            type=db.ProjectType.WORKFLOW,
        )
        db_session.add(test_workflow)

        # Create workflow in different organization
        other_org_id = uuid.uuid4()
        other_workflow_id = uuid.uuid4()
        other_workflow = db.WorkflowProject(
            id=other_workflow_id,
            name="Other Workflow",
            organization_id=other_org_id,
            type=db.ProjectType.WORKFLOW,
        )
        db_session.add(other_workflow)
        db_session.commit()

        results = get_workflows_by_organization(db_session, test_organization)

        workflow_ids = [w.id for w in results]
        assert test_workflow_id in workflow_ids
        assert other_workflow_id not in workflow_ids

    def test_returns_empty_list_for_organization_with_no_workflows(
        self, db_session: Session
    ):
        """
        Test that empty list is returned for organization with no workflows.
        """
        empty_org_id = uuid.uuid4()
        results = get_workflows_by_organization(db_session, empty_org_id)

        assert isinstance(results, list)
        assert len(results) == 0

    def test_returns_workflow_projects_not_agents(
        self, db_session: Session, test_organization
    ):
        """
        Test that only workflows are returned, not agent projects.
        """
        # Create a workflow
        workflow_id = uuid.uuid4()
        workflow = db.WorkflowProject(
            id=workflow_id,
            name="Workflow",
            organization_id=test_organization,
            type=db.ProjectType.WORKFLOW,
        )
        db_session.add(workflow)

        # Create an agent (should not be included)
        agent_id = uuid.uuid4()
        agent = db.AgentProject(
            id=agent_id,
            name="Agent",
            organization_id=test_organization,
            type=db.ProjectType.AGENT,
        )
        db_session.add(agent)
        db_session.commit()

        results = get_workflows_by_organization(db_session, test_organization)

        # Should only include workflows, not agents
        result_ids = [w.id for w in results]
        assert workflow_id in result_ids
        assert agent_id not in result_ids

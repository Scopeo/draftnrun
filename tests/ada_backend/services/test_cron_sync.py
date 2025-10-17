"""
Integration test for cron job sync functionality.

This test mimics the frontend flow:
1. Create a project with a workflow
2. Create a Start node component with cron parameters
3. Save the graph via the updateGraph endpoint
4. Call the sync-cron endpoint
5. Verify the cron job was created in the scheduler
"""

import pytest
from uuid import uuid4
from sqlalchemy.orm import Session

from ada_backend.database.models import (
    Component,
    ComponentInstance,
    ComponentParameterDefinition,
    BasicParameter,
    ToolDescription,
    GraphRunner,
    ComponentNode,
    WorkflowProject,
    ProjectEnvironmentBinding,
    EnvType,
    CronEntrypoint,
)
from ada_backend.services.cron.service import sync_project_cron_jobs
from ada_backend.repositories.cron_repository import get_cron_jobs_by_organization


@pytest.fixture
def setup_test_data(session: Session):
    """Set up test data mimicking the frontend flow."""
    org_id = uuid4()
    project_id = uuid4()
    user_id = str(uuid4())

    # Create a Start component (this should exist in the system)
    start_component_id = uuid4()
    start_component = Component(
        id=start_component_id,
        name="Start",
        description="Start node component",
        callable=False,
        python_import_path="engine.agent.inputs_outputs.start",
        python_class_name="Start",
        release_stage="public",
        organization_id=None,  # Global component
        is_input=True,
        is_output=False,
        icon="mdi-play",
    )
    session.add(start_component)

    # Create tool description for Start component
    tool_desc = ToolDescription(
        id=uuid4(),
        component_id=start_component_id,
        name="Start_Tool",
        description="A start node that initializes the workflow with input data",
    )
    session.add(tool_desc)

    # Create parameter definitions for the Start component
    cron_enabled_param_def = ComponentParameterDefinition(
        id=uuid4(),
        component_id=start_component_id,
        name="cron_enabled",
        type="boolean",
        default=False,
        nullable=False,
        description="Enable cron scheduling",
        order=1,
    )
    session.add(cron_enabled_param_def)

    cron_expression_param_def = ComponentParameterDefinition(
        id=uuid4(),
        component_id=start_component_id,
        name="cron_expression",
        type="string",
        default="0 9 * * 1-5",
        nullable=False,
        description="Cron expression for scheduling",
        order=2,
    )
    session.add(cron_expression_param_def)

    cron_timezone_param_def = ComponentParameterDefinition(
        id=uuid4(),
        component_id=start_component_id,
        name="cron_timezone",
        type="string",
        default="UTC",
        nullable=False,
        description="Timezone for cron scheduling",
        order=3,
    )
    session.add(cron_timezone_param_def)

    # Create a workflow project
    project = WorkflowProject(
        id=project_id,
        name="Test Cron Workflow",
        description="Test workflow with cron scheduling",
        organization_id=org_id,
        type="workflow",
    )
    session.add(project)

    # Create a draft graph runner
    graph_runner_id = uuid4()
    graph_runner = GraphRunner(
        id=graph_runner_id,
        tag_version=None,
    )
    session.add(graph_runner)

    # Bind graph runner to project as DRAFT
    binding = ProjectEnvironmentBinding(
        project_id=project_id,
        graph_runner_id=graph_runner_id,
        environment=EnvType.DRAFT,
    )
    session.add(binding)

    # Create a Start component instance
    component_instance_id = uuid4()
    component_instance = ComponentInstance(
        id=component_instance_id,
        name="Start Node",
        component_id=start_component_id,
        tool_description_id=tool_desc.id,
        is_agent=False,
    )
    session.add(component_instance)

    # Add the component instance to the graph as a start node
    component_node = ComponentNode(
        graph_runner_id=graph_runner_id,
        component_instance_id=component_instance_id,
        is_start_node=True,
    )
    session.add(component_node)

    # Add cron parameters to the component instance
    # cron_enabled = True
    cron_enabled_param = BasicParameter(
        id=uuid4(),
        component_instance_id=component_instance_id,
        parameter_definition_id=cron_enabled_param_def.id,
        value="true",  # Boolean stored as string
        order=1,
    )
    session.add(cron_enabled_param)

    # cron_expression = "*/1 * * * *" (every minute)
    cron_expression_param = BasicParameter(
        id=uuid4(),
        component_instance_id=component_instance_id,
        parameter_definition_id=cron_expression_param_def.id,
        value="*/1 * * * *",
        order=2,
    )
    session.add(cron_expression_param)

    # cron_timezone = "UTC"
    cron_timezone_param = BasicParameter(
        id=uuid4(),
        component_instance_id=component_instance_id,
        parameter_definition_id=cron_timezone_param_def.id,
        value="UTC",
        order=3,
    )
    session.add(cron_timezone_param)

    session.commit()

    return {
        "org_id": org_id,
        "project_id": project_id,
        "user_id": user_id,
        "graph_runner_id": graph_runner_id,
        "component_instance_id": component_instance_id,
        "start_component_id": start_component_id,
    }


def test_cron_sync_creates_job(session: Session, setup_test_data):
    """Test that syncing creates a cron job when cron is enabled."""
    data = setup_test_data

    # Call the sync function (this is what the frontend does after saving)
    result = sync_project_cron_jobs(
        session=session,
        project_id=data["project_id"],
        user_id=data["user_id"],
    )

    # Verify the result
    assert result["status"] == "success"
    assert len(result["created"]) == 1
    assert len(result["updated"]) == 0
    assert result["errors"] is None

    # Verify the cron job was created in the database
    cron_jobs = get_cron_jobs_by_organization(session, data["org_id"], enabled_only=False)
    assert len(cron_jobs) == 1

    cron_job = cron_jobs[0]
    assert cron_job.name == "Test Cron Workflow - Draft (Auto-scheduled)"
    assert cron_job.cron_expr == "*/1 * * * *"
    assert cron_job.tz == "UTC"
    assert cron_job.entrypoint == CronEntrypoint.AGENT_INFERENCE
    assert cron_job.is_enabled is True
    assert cron_job.organization_id == data["org_id"]

    # Verify the payload
    assert cron_job.payload["project_id"] == str(data["project_id"])
    assert cron_job.payload["env"] == "draft"
    assert "input_data" in cron_job.payload


def test_cron_sync_updates_existing_job(session: Session, setup_test_data):
    """Test that syncing updates an existing cron job."""
    data = setup_test_data

    # First sync - creates the job
    result1 = sync_project_cron_jobs(
        session=session,
        project_id=data["project_id"],
        user_id=data["user_id"],
    )
    assert len(result1["created"]) == 1

    # Get the created job
    cron_jobs = get_cron_jobs_by_organization(session, data["org_id"], enabled_only=False)
    assert len(cron_jobs) == 1
    original_job_id = cron_jobs[0].id

    # Update the cron expression in the component instance
    component_instance = session.query(ComponentInstance).filter_by(
        id=data["component_instance_id"]
    ).first()

    # Find and update the cron_expression parameter
    for param in component_instance.basic_parameters:
        if param.parameter_definition.name == "cron_expression":
            param.value = "*/5 * * * *"  # Change to every 5 minutes
            break
    session.commit()

    # Second sync - should update the job
    result2 = sync_project_cron_jobs(
        session=session,
        project_id=data["project_id"],
        user_id=data["user_id"],
    )

    assert result2["status"] == "success"
    assert len(result2["created"]) == 0
    assert len(result2["updated"]) == 1
    assert str(original_job_id) in result2["updated"]

    # Verify the job was updated
    cron_jobs = get_cron_jobs_by_organization(session, data["org_id"], enabled_only=False)
    assert len(cron_jobs) == 1
    assert cron_jobs[0].id == original_job_id
    assert cron_jobs[0].cron_expr == "*/5 * * * *"


def test_cron_sync_pauses_disabled_job(session: Session, setup_test_data):
    """Test that syncing pauses a cron job when cron is disabled."""
    data = setup_test_data

    # First sync - creates the job
    result1 = sync_project_cron_jobs(
        session=session,
        project_id=data["project_id"],
        user_id=data["user_id"],
    )
    assert len(result1["created"]) == 1

    # Verify job is enabled
    cron_jobs = get_cron_jobs_by_organization(session, data["org_id"], enabled_only=False)
    assert cron_jobs[0].is_enabled is True
    original_job_id = cron_jobs[0].id

    # Disable cron in the component instance
    component_instance = session.query(ComponentInstance).filter_by(
        id=data["component_instance_id"]
    ).first()

    for param in component_instance.basic_parameters:
        if param.parameter_definition.name == "cron_enabled":
            param.value = "false"
            break
    session.commit()

    # Second sync - should pause the job
    result2 = sync_project_cron_jobs(
        session=session,
        project_id=data["project_id"],
        user_id=data["user_id"],
    )

    assert result2["status"] == "success"
    assert len(result2["updated"]) == 1

    # Verify the job was paused
    cron_jobs = get_cron_jobs_by_organization(session, data["org_id"], enabled_only=False)
    assert len(cron_jobs) == 1
    assert cron_jobs[0].id == original_job_id
    assert cron_jobs[0].is_enabled is False


def test_cron_sync_no_start_node(session: Session):
    """Test sync with no start node returns appropriate status."""
    org_id = uuid4()
    project_id = uuid4()
    user_id = str(uuid4())

    # Create project with graph but no start node
    project = WorkflowProject(
        id=project_id,
        name="Test Project No Start",
        organization_id=org_id,
        type="workflow",
    )
    session.add(project)

    graph_runner = GraphRunner(id=uuid4())
    session.add(graph_runner)

    binding = ProjectEnvironmentBinding(
        project_id=project_id,
        graph_runner_id=graph_runner.id,
        environment=EnvType.DRAFT,
    )
    session.add(binding)
    session.commit()

    result = sync_project_cron_jobs(session, project_id, user_id)

    assert result["status"] == "no_start_nodes"
    assert result["message"] == "No start nodes found in draft graph"
    assert len(result["created"]) == 0

"""Unit tests for the field expression autocomplete service.

These tests use pytest-mock-resources to create an ephemeral PostgreSQL instance,
avoiding the need for external database credentials while supporting PostgreSQL
features like ENUM types.
"""

from uuid import uuid4

import pytest
from pytest_mock_resources import create_postgres_fixture
from sqlalchemy.orm import Session, sessionmaker

from ada_backend.database import models as db
from ada_backend.database.models import Base
from ada_backend.schemas.pipeline.field_expression_schema import FieldExpressionAutocompleteRequest
from ada_backend.services.graph.field_expression_autocomplete_service import autocomplete_field_expression

# Create a PostgreSQL fixture for these tests
pg_engine = create_postgres_fixture()


@pytest.fixture
def pg_session(pg_engine):
    """Create a PostgreSQL session with tables for testing."""
    # Create schemas required by models
    with pg_engine.connect() as conn:
        conn.execute(db.sa.text("CREATE SCHEMA IF NOT EXISTS scheduler"))
        conn.execute(db.sa.text("CREATE SCHEMA IF NOT EXISTS quality_assurance"))
        conn.execute(db.sa.text("CREATE SCHEMA IF NOT EXISTS credits"))
        conn.execute(db.sa.text("CREATE SCHEMA IF NOT EXISTS widget"))
        conn.execute(db.sa.text("CREATE SCHEMA IF NOT EXISTS traces"))
        conn.commit()

    Base.metadata.create_all(bind=pg_engine)
    SessionLocal = sessionmaker(bind=pg_engine)
    connection = pg_engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def test_graph_setup(pg_session: Session):
    """Create test data: project, graph_runner, component instances, edges, and ports."""
    session = pg_session

    # Create project
    project = db.WorkflowProject(id=uuid4(), name="Test Project", organization_id=uuid4())
    session.add(project)
    session.flush()

    # Create graph runner
    graph_runner = db.GraphRunner(id=uuid4())
    session.add(graph_runner)
    session.flush()

    # Bind graph runner to project
    env_binding = db.ProjectEnvironmentBinding(
        project_id=project.id,
        graph_runner_id=graph_runner.id,
        environment=db.EnvType.DRAFT,
    )
    session.add(env_binding)
    session.flush()

    # Create component and component version
    component = db.Component(id=uuid4(), name="TestComponent")
    session.add(component)
    session.flush()

    component_version = db.ComponentVersion(
        id=uuid4(),
        component_id=component.id,
        version_tag="1.0.0",
    )
    session.add(component_version)
    session.flush()

    # Create output port definition
    output_port = db.PortDefinition(
        id=uuid4(),
        component_version_id=component_version.id,
        name="output",
        port_type=db.PortType.OUTPUT,
    )
    session.add(output_port)
    session.flush()

    # Create component instances
    upstream_instance = db.ComponentInstance(
        id=uuid4(),
        component_version_id=component_version.id,
        name="Upstream Agent",
    )
    target_instance = db.ComponentInstance(
        id=uuid4(),
        component_version_id=component_version.id,
        name="Target Agent",
    )
    downstream_instance = db.ComponentInstance(
        id=uuid4(),
        component_version_id=component_version.id,
        name="Downstream Agent",
    )
    session.add_all([upstream_instance, target_instance, downstream_instance])
    session.flush()

    # Create graph runner nodes
    upstream_node = db.GraphRunnerNode(
        node_id=upstream_instance.id,
        graph_runner_id=graph_runner.id,
        node_type=db.NodeType.COMPONENT,
        is_start_node=True,
    )
    target_node = db.GraphRunnerNode(
        node_id=target_instance.id,
        graph_runner_id=graph_runner.id,
        node_type=db.NodeType.COMPONENT,
        is_start_node=False,
    )
    downstream_node = db.GraphRunnerNode(
        node_id=downstream_instance.id,
        graph_runner_id=graph_runner.id,
        node_type=db.NodeType.COMPONENT,
        is_start_node=False,
    )
    session.add_all([upstream_node, target_node, downstream_node])
    session.flush()

    # Create edges: upstream -> target -> downstream
    edge1 = db.GraphRunnerEdge(
        id=uuid4(),
        source_node_id=upstream_instance.id,
        target_node_id=target_instance.id,
        graph_runner_id=graph_runner.id,
        order=0,
    )
    edge2 = db.GraphRunnerEdge(
        id=uuid4(),
        source_node_id=target_instance.id,
        target_node_id=downstream_instance.id,
        graph_runner_id=graph_runner.id,
        order=1,
    )
    session.add_all([edge1, edge2])
    session.commit()

    return {
        "session": session,
        "project": project,
        "graph_runner": graph_runner,
        "upstream_instance": upstream_instance,
        "target_instance": target_instance,
        "downstream_instance": downstream_instance,
        "component_version": component_version,
    }


def test_instance_suggestions_partial_match(test_graph_setup):
    """Test that partial UUID match returns matching instance suggestions."""
    session = test_graph_setup["session"]
    project = test_graph_setup["project"]
    graph_runner = test_graph_setup["graph_runner"]
    upstream_instance = test_graph_setup["upstream_instance"]
    target_instance = test_graph_setup["target_instance"]

    # Query with partial UUID of upstream instance
    partial_uuid = str(upstream_instance.id)[:8]
    request = FieldExpressionAutocompleteRequest(
        target_instance_id=target_instance.id,
        query=partial_uuid,
    )

    response = autocomplete_field_expression(
        session=session,
        project_id=project.id,
        graph_runner_id=graph_runner.id,
        request=request,
    )

    assert len(response.suggestions) >= 1
    assert any(s.id == str(upstream_instance.id) for s in response.suggestions)
    assert all(s.kind == "module" for s in response.suggestions)
    # Check insert_text has trailing dot
    matching = [s for s in response.suggestions if s.id == str(upstream_instance.id)]
    assert len(matching) == 1
    assert matching[0].insert_text == f"{upstream_instance.id}."


def test_instance_suggestions_name_match(test_graph_setup):
    """Test that instance name match returns matching instance suggestions."""
    session = test_graph_setup["session"]
    project = test_graph_setup["project"]
    graph_runner = test_graph_setup["graph_runner"]
    upstream_instance = test_graph_setup["upstream_instance"]
    target_instance = test_graph_setup["target_instance"]

    # Query with partial name
    request = FieldExpressionAutocompleteRequest(
        target_instance_id=target_instance.id,
        query="Upstream",
    )

    response = autocomplete_field_expression(
        session=session,
        project_id=project.id,
        graph_runner_id=graph_runner.id,
        request=request,
    )

    assert len(response.suggestions) == 1
    assert response.suggestions[0].id == str(upstream_instance.id)
    assert response.suggestions[0].label == "Upstream Agent"


def test_port_suggestions(test_graph_setup):
    """Test that port suggestions are returned for property phase."""
    session = test_graph_setup["session"]
    project = test_graph_setup["project"]
    graph_runner = test_graph_setup["graph_runner"]
    upstream_instance = test_graph_setup["upstream_instance"]
    target_instance = test_graph_setup["target_instance"]

    # Query with instance UUID and partial port name
    request = FieldExpressionAutocompleteRequest(
        target_instance_id=target_instance.id,
        query=f"{upstream_instance.id}.out",
    )

    response = autocomplete_field_expression(
        session=session,
        project_id=project.id,
        graph_runner_id=graph_runner.id,
        request=request,
    )

    assert len(response.suggestions) >= 1
    assert any(s.label == "output" for s in response.suggestions)
    assert all(s.kind == "property" for s in response.suggestions)
    # Check insert_text has closing braces
    output_match = [s for s in response.suggestions if s.label == "output"]
    assert len(output_match) == 1
    assert output_match[0].insert_text == "output}}"


def test_filters_downstream_instances(test_graph_setup):
    """Test that downstream instances are filtered out from suggestions."""
    session = test_graph_setup["session"]
    project = test_graph_setup["project"]
    graph_runner = test_graph_setup["graph_runner"]
    upstream_instance = test_graph_setup["upstream_instance"]
    target_instance = test_graph_setup["target_instance"]
    downstream_instance = test_graph_setup["downstream_instance"]

    # Query with empty string to get all upstream instances
    request = FieldExpressionAutocompleteRequest(
        target_instance_id=target_instance.id,
        query="",
    )

    response = autocomplete_field_expression(
        session=session,
        project_id=project.id,
        graph_runner_id=graph_runner.id,
        request=request,
    )

    # Upstream instance should be in suggestions
    assert any(s.id == str(upstream_instance.id) for s in response.suggestions)
    # Downstream instance should NOT be in suggestions
    assert all(s.id != str(downstream_instance.id) for s in response.suggestions)
    # Target instance itself should NOT be in suggestions
    assert all(s.id != str(target_instance.id) for s in response.suggestions)


def test_empty_query_returns_all_upstream(test_graph_setup):
    """Test that empty query returns all upstream instances."""
    session = test_graph_setup["session"]
    project = test_graph_setup["project"]
    graph_runner = test_graph_setup["graph_runner"]
    upstream_instance = test_graph_setup["upstream_instance"]
    target_instance = test_graph_setup["target_instance"]

    request = FieldExpressionAutocompleteRequest(
        target_instance_id=target_instance.id,
        query="",
    )

    response = autocomplete_field_expression(
        session=session,
        project_id=project.id,
        graph_runner_id=graph_runner.id,
        request=request,
    )

    assert len(response.suggestions) >= 1
    assert any(s.id == str(upstream_instance.id) for s in response.suggestions)


def test_downstream_instance_port_query_returns_empty(test_graph_setup):
    """Test that querying ports for a downstream instance returns no suggestions."""
    session = test_graph_setup["session"]
    project = test_graph_setup["project"]
    graph_runner = test_graph_setup["graph_runner"]
    target_instance = test_graph_setup["target_instance"]
    downstream_instance = test_graph_setup["downstream_instance"]

    # Query with downstream instance UUID (which is not upstream of target)
    request = FieldExpressionAutocompleteRequest(
        target_instance_id=target_instance.id,
        query=f"{downstream_instance.id}.ou",
    )

    response = autocomplete_field_expression(
        session=session,
        project_id=project.id,
        graph_runner_id=graph_runner.id,
        request=request,
    )

    # Should return no suggestions since downstream is not upstream of target
    assert response.suggestions == []


def test_no_upstream_instances_returns_empty(pg_session: Session):
    """Test that a node with no upstream instances returns empty suggestions."""
    session = pg_session

    # Create isolated setup with only one node (no edges)
    project = db.WorkflowProject(id=uuid4(), name="Isolated Project", organization_id=uuid4())
    session.add(project)
    session.flush()

    graph_runner = db.GraphRunner(id=uuid4())
    session.add(graph_runner)
    session.flush()

    env_binding = db.ProjectEnvironmentBinding(
        project_id=project.id,
        graph_runner_id=graph_runner.id,
        environment=db.EnvType.DRAFT,
    )
    session.add(env_binding)
    session.flush()

    component = db.Component(id=uuid4(), name="IsolatedComponent")
    session.add(component)
    session.flush()

    component_version = db.ComponentVersion(
        id=uuid4(),
        component_id=component.id,
        version_tag="1.0.0",
    )
    session.add(component_version)
    session.flush()

    instance = db.ComponentInstance(
        id=uuid4(),
        component_version_id=component_version.id,
        name="Isolated Instance",
    )
    session.add(instance)
    session.flush()

    node = db.GraphRunnerNode(
        node_id=instance.id,
        graph_runner_id=graph_runner.id,
        node_type=db.NodeType.COMPONENT,
        is_start_node=True,
    )
    session.add(node)
    session.commit()

    request = FieldExpressionAutocompleteRequest(
        target_instance_id=instance.id,
        query="",
    )

    response = autocomplete_field_expression(
        session=session,
        project_id=project.id,
        graph_runner_id=graph_runner.id,
        request=request,
    )

    # Node has no upstream instances, so suggestions should be empty
    assert response.suggestions == []

from unittest.mock import patch
from uuid import uuid4

import pytest

from ada_backend.database import models as db
from ada_backend.database.models import EnvType, ParameterType
from ada_backend.database.setup_db import get_db_session
from ada_backend.repositories.component_repository import get_component_instance_by_id
from ada_backend.repositories.edge_repository import get_edges
from ada_backend.repositories.graph_runner_repository import get_component_nodes
from ada_backend.schemas.parameter_schema import ParameterKind, PipelineParameterSchema
from ada_backend.schemas.pipeline.component_instance_schema import (
    ComponentInstanceDeleteResponse,
    ComponentInstanceUpdateResponse,
    ComponentInstanceUpdateSchema,
)
from ada_backend.schemas.pipeline.field_expression_schema import FieldExpressionUpdateSchema
from ada_backend.services.graph.component_instance_service import (
    delete_component_instance_service,
    upsert_component_instance_service,
)
from ada_backend.services.project_service import delete_project_service
from tests.ada_backend.test_utils import create_project_and_graph_runner
from tests.mocks.ada_backend_db import MOCK_UUIDS

MOCK_AGENT_SERVICE_PATH = "ada_backend.services.graph.component_instance_service.get_agent_for_project"


@pytest.mark.asyncio
async def test_create_new_component_instance():
    """Test creating a new component instance in a draft graph"""
    with get_db_session() as session:
        project_id, graph_runner_id = create_project_and_graph_runner(
            session, project_name_prefix="create_component_test", description="Test project"
        )

        component_version_id = MOCK_UUIDS["component_version_1"]
        component_id = MOCK_UUIDS["component_1"]

        new_component_id = uuid4()
        component_data = ComponentInstanceUpdateSchema(
            id=new_component_id,
            name="Test Component",
            ref="test_comp",
            is_start_node=False,
            component_id=component_id,
            component_version_id=component_version_id,
            parameters=[
                PipelineParameterSchema(
                    name="model",
                    value="gpt-4",
                    type=ParameterType.STRING,
                )
            ],
            field_expressions=[],
            port_mappings=[],
        )

        with patch(MOCK_AGENT_SERVICE_PATH):
            response = await upsert_component_instance_service(
                session=session,
                graph_runner_id=graph_runner_id,
                project_id=project_id,
                component_data=component_data,
                user_id=uuid4(),
            )

        assert isinstance(response, ComponentInstanceUpdateResponse)
        assert response.component_instance_id == new_component_id
        assert response.graph_runner_id == graph_runner_id
        assert response.last_edited_time is not None

        component = get_component_instance_by_id(session, new_component_id)
        assert component is not None
        assert component.component_version_id == component_version_id

        graph_nodes = get_component_nodes(session, graph_runner_id)
        node_ids = [node.id for node in graph_nodes]
        assert new_component_id in node_ids

        delete_project_service(session=session, project_id=project_id)


@pytest.mark.asyncio
async def test_update_existing_component_instance():
    """Test updating an existing component instance"""
    with get_db_session() as session:
        project_id, graph_runner_id = create_project_and_graph_runner(
            session, project_name_prefix="update_component_test", description="Test project"
        )

        component_version_id = MOCK_UUIDS["component_version_1"]
        component_id = MOCK_UUIDS["component_1"]

        existing_component_id = uuid4()
        component_instance = db.ComponentInstance(
            id=existing_component_id,
            component_version_id=component_version_id,
        )
        session.add(component_instance)
        session.commit()

        graph_node = db.GraphRunnerNode(
            node_id=existing_component_id,
            graph_runner_id=graph_runner_id,
            node_type=db.NodeType.COMPONENT,
            is_start_node=True,
        )
        session.add(graph_node)
        session.commit()

        component_data = ComponentInstanceUpdateSchema(
            id=existing_component_id,
            name="Updated Component",
            ref="updated_comp",
            is_start_node=True,
            component_id=component_id,
            component_version_id=component_version_id,
            parameters=[
                PipelineParameterSchema(
                    name="temperature",
                    value="0.7",
                    type=ParameterType.FLOAT,
                )
            ],
            field_expressions=[],
            port_mappings=[],
        )

        with patch(MOCK_AGENT_SERVICE_PATH):
            response = await upsert_component_instance_service(
                session=session,
                graph_runner_id=graph_runner_id,
                project_id=project_id,
                component_data=component_data,
                user_id=uuid4(),
            )

        assert response.component_instance_id == existing_component_id

        component = get_component_instance_by_id(session, existing_component_id)
        assert component is not None

        delete_project_service(session=session, project_id=project_id)


@pytest.mark.asyncio
async def test_upsert_with_field_expressions():
    """Test upserting component with field expressions"""
    with get_db_session() as session:
        project_id, graph_runner_id = create_project_and_graph_runner(
            session, project_name_prefix="field_expressions_test", description="Test project"
        )

        component_version_id = MOCK_UUIDS["component_version_1"]
        component_id = MOCK_UUIDS["component_1"]

        new_component_id = uuid4()
        component_data = ComponentInstanceUpdateSchema(
            id=new_component_id,
            name="Component with Expressions",
            ref="expr_comp",
            is_start_node=False,
            component_id=component_id,
            component_version_id=component_version_id,
            parameters=[],
            field_expressions=[
                FieldExpressionUpdateSchema(
                    field_name="prompt",
                    expression_json='{"type": "literal", "value": "Hello"}',
                )
            ],
            port_mappings=[],
        )

        with patch(MOCK_AGENT_SERVICE_PATH):
            response = await upsert_component_instance_service(
                session=session,
                graph_runner_id=graph_runner_id,
                project_id=project_id,
                component_data=component_data,
                user_id=uuid4(),
            )

        assert response.component_instance_id == new_component_id

        component = get_component_instance_by_id(session, new_component_id)
        assert component is not None

        delete_project_service(session=session, project_id=project_id)


@pytest.mark.asyncio
async def test_upsert_with_input_parameters():
    """Test upserting component with INPUT kind parameters (converted to field expressions)"""
    with get_db_session() as session:
        project_id, graph_runner_id = create_project_and_graph_runner(
            session, project_name_prefix="input_parameters_test", description="Test project"
        )

        component_version_id = MOCK_UUIDS["component_version_1"]
        component_id = MOCK_UUIDS["component_1"]

        new_component_id = uuid4()
        component_data = ComponentInstanceUpdateSchema(
            id=new_component_id,
            name="Component with Inputs",
            ref="input_comp",
            is_start_node=False,
            component_id=component_id,
            component_version_id=component_version_id,
            parameters=[
                PipelineParameterSchema(
                    name="messages",
                    value='{"type": "literal", "value": "test"}',
                    type=ParameterType.JSON,
                    kind=ParameterKind.INPUT,
                )
            ],
            field_expressions=[],
            port_mappings=[],
        )

        with patch(MOCK_AGENT_SERVICE_PATH):
            response = await upsert_component_instance_service(
                session=session,
                graph_runner_id=graph_runner_id,
                project_id=project_id,
                component_data=component_data,
                user_id=uuid4(),
            )

        assert response.component_instance_id == new_component_id

        delete_project_service(session=session, project_id=project_id)


@pytest.mark.asyncio
async def test_upsert_fails_on_production_graph():
    """Test that upserting fails on a production (non-draft) graph"""
    with get_db_session() as session:
        project_id, _ = create_project_and_graph_runner(
            session, project_name_prefix="production_upsert_fail_test", description="Test project"
        )

        component_version_id = MOCK_UUIDS["component_version_1"]
        component_id = MOCK_UUIDS["component_1"]

        prod_graph_id = uuid4()
        graph_runner = db.GraphRunner(id=prod_graph_id, tag_version="v1.0.0")
        session.add(graph_runner)
        session.commit()

        binding = db.ProjectEnvironmentBinding(
            project_id=project_id, graph_runner_id=prod_graph_id, environment=EnvType.PRODUCTION
        )
        session.add(binding)
        session.commit()

        new_component_id = uuid4()
        component_data = ComponentInstanceUpdateSchema(
            id=new_component_id,
            name="Test Component",
            ref="test_comp",
            is_start_node=False,
            component_id=component_id,
            component_version_id=component_version_id,
            parameters=[],
            field_expressions=[],
            port_mappings=[],
        )

        with pytest.raises(ValueError, match="only draft versions"):
            await upsert_component_instance_service(
                session=session,
                graph_runner_id=prod_graph_id,
                project_id=project_id,
                component_data=component_data,
                user_id=uuid4(),
            )

        delete_project_service(session=session, project_id=project_id)


@pytest.mark.asyncio
async def test_upsert_fails_on_nonexistent_graph():
    """Test that upserting fails if graph doesn't exist"""
    with get_db_session() as session:
        project_id, _ = create_project_and_graph_runner(
            session, project_name_prefix="nonexistent_graph_test", description="Test project"
        )

        component_version_id = MOCK_UUIDS["component_version_1"]
        component_id = MOCK_UUIDS["component_1"]

        nonexistent_graph_id = uuid4()
        new_component_id = uuid4()

        component_data = ComponentInstanceUpdateSchema(
            id=new_component_id,
            name="Test Component",
            ref="test_comp",
            is_start_node=False,
            component_id=component_id,
            component_version_id=component_version_id,
            parameters=[],
            field_expressions=[],
            port_mappings=[],
        )

        with pytest.raises(ValueError, match="not found"):
            await upsert_component_instance_service(
                session=session,
                graph_runner_id=nonexistent_graph_id,
                project_id=project_id,
                component_data=component_data,
                user_id=uuid4(),
            )

        delete_project_service(session=session, project_id=project_id)


def test_delete_component_instance():
    """Test deleting a component instance from a graph"""
    with get_db_session() as session:
        project_id, graph_runner_id = create_project_and_graph_runner(
            session, project_name_prefix="delete_component_test", description="Test project"
        )

        component_version_id = MOCK_UUIDS["component_version_1"]

        component_id = uuid4()
        component_instance_1 = db.ComponentInstance(
            id=component_id,
            component_version_id=component_version_id,
        )
        session.add(component_instance_1)
        session.commit()

        graph_node_1 = db.GraphRunnerNode(
            node_id=component_id,
            graph_runner_id=graph_runner_id,
            node_type=db.NodeType.COMPONENT,
            is_start_node=True,
        )
        session.add(graph_node_1)
        session.commit()

        component_instance_2 = db.ComponentInstance(
            id=uuid4(),
            component_version_id=component_version_id,
        )
        session.add(component_instance_2)
        session.commit()

        graph_node_2 = db.GraphRunnerNode(
            node_id=component_instance_2.id,
            graph_runner_id=graph_runner_id,
            node_type=db.NodeType.COMPONENT,
            is_start_node=False,
        )
        session.add(graph_node_2)
        session.commit()

        edge_id = uuid4()
        edge = db.GraphRunnerEdge(
            id=edge_id,
            source_node_id=component_id,
            target_node_id=component_instance_2.id,
            graph_runner_id=graph_runner_id,
        )
        session.add(edge)
        session.commit()

        edges_before = get_edges(session, graph_runner_id)
        assert len(edges_before) == 1

        response = delete_component_instance_service(
            session=session,
            graph_runner_id=graph_runner_id,
            component_instance_id=component_id,
        )

        assert isinstance(response, ComponentInstanceDeleteResponse)
        assert response.component_instance_id == component_id
        assert response.graph_runner_id == graph_runner_id
        assert len(response.deleted_edge_ids) == 1
        assert edge_id in response.deleted_edge_ids

        graph_nodes = get_component_nodes(session, graph_runner_id)
        node_ids = [node.id for node in graph_nodes]
        assert component_id not in node_ids

        edges_after = get_edges(session, graph_runner_id)
        assert len(edges_after) == 0

        delete_project_service(session=session, project_id=project_id)


def test_delete_component_with_multiple_edges():
    """Test deleting a component that has multiple connected edges"""
    with get_db_session() as session:
        project_id, graph_runner_id = create_project_and_graph_runner(
            session, project_name_prefix="delete_multiple_edges_test", description="Test project"
        )

        component_version_id = MOCK_UUIDS["component_version_1"]

        component_id = uuid4()
        component_1 = db.ComponentInstance(
            id=component_id,
            component_version_id=component_version_id,
        )
        component_2 = db.ComponentInstance(
            id=uuid4(),
            component_version_id=component_version_id,
        )
        component_3 = db.ComponentInstance(
            id=uuid4(),
            component_version_id=component_version_id,
        )
        session.add_all([component_1, component_2, component_3])
        session.commit()

        for comp in [component_1, component_2, component_3]:
            node = db.GraphRunnerNode(
                node_id=comp.id,
                graph_runner_id=graph_runner_id,
                node_type=db.NodeType.COMPONENT,
                is_start_node=(comp.id == component_id),
            )
            session.add(node)
        session.commit()

        edge_1_id = uuid4()
        edge_2_id = uuid4()
        edge_1 = db.GraphRunnerEdge(
            id=edge_1_id,
            source_node_id=component_id,
            target_node_id=component_2.id,
            graph_runner_id=graph_runner_id,
        )
        edge_2 = db.GraphRunnerEdge(
            id=edge_2_id,
            source_node_id=component_id,
            target_node_id=component_3.id,
            graph_runner_id=graph_runner_id,
        )
        session.add_all([edge_1, edge_2])
        session.commit()

        response = delete_component_instance_service(
            session=session,
            graph_runner_id=graph_runner_id,
            component_instance_id=component_id,
        )

        assert len(response.deleted_edge_ids) == 2
        assert edge_1_id in response.deleted_edge_ids
        assert edge_2_id in response.deleted_edge_ids

        edges_after = get_edges(session, graph_runner_id)
        for edge in edges_after:
            assert edge.source_node_id != component_id
            assert edge.target_node_id != component_id

        delete_project_service(session=session, project_id=project_id)


def test_delete_component_with_incoming_and_outgoing_edges():
    """Test deleting a component that has both incoming and outgoing edges"""
    with get_db_session() as session:
        project_id, graph_runner_id = create_project_and_graph_runner(
            session, project_name_prefix="delete_bidirectional_edges_test", description="Test project"
        )

        component_version_id = MOCK_UUIDS["component_version_1"]

        component_id = uuid4()
        upstream_comp = db.ComponentInstance(
            id=uuid4(),
            component_version_id=component_version_id,
        )
        middle_comp = db.ComponentInstance(
            id=component_id,
            component_version_id=component_version_id,
        )
        downstream_comp = db.ComponentInstance(
            id=uuid4(),
            component_version_id=component_version_id,
        )
        session.add_all([upstream_comp, middle_comp, downstream_comp])
        session.commit()

        for comp in [upstream_comp, middle_comp, downstream_comp]:
            node = db.GraphRunnerNode(
                node_id=comp.id,
                graph_runner_id=graph_runner_id,
                node_type=db.NodeType.COMPONENT,
                is_start_node=False,
            )
            session.add(node)
        session.commit()

        edge_in_id = uuid4()
        edge_out_id = uuid4()
        edge_in = db.GraphRunnerEdge(
            id=edge_in_id,
            source_node_id=upstream_comp.id,
            target_node_id=component_id,
            graph_runner_id=graph_runner_id,
        )
        edge_out = db.GraphRunnerEdge(
            id=edge_out_id,
            source_node_id=component_id,
            target_node_id=downstream_comp.id,
            graph_runner_id=graph_runner_id,
        )
        session.add_all([edge_in, edge_out])
        session.commit()

        response = delete_component_instance_service(
            session=session,
            graph_runner_id=graph_runner_id,
            component_instance_id=component_id,
        )

        assert len(response.deleted_edge_ids) == 2
        assert edge_in_id in response.deleted_edge_ids
        assert edge_out_id in response.deleted_edge_ids

        delete_project_service(session=session, project_id=project_id)


def test_delete_fails_on_production_graph():
    """Test that deletion fails on a production (non-draft) graph"""
    with get_db_session() as session:
        project_id, _ = create_project_and_graph_runner(
            session, project_name_prefix="production_delete_fail_test", description="Test project"
        )

        component_version_id = MOCK_UUIDS["component_version_1"]

        prod_graph_id = uuid4()
        graph_runner = db.GraphRunner(id=prod_graph_id, tag_version="v1.0.0")
        session.add(graph_runner)
        session.commit()

        binding = db.ProjectEnvironmentBinding(
            project_id=project_id, graph_runner_id=prod_graph_id, environment=EnvType.PRODUCTION
        )
        session.add(binding)
        session.commit()

        component = db.ComponentInstance(
            id=uuid4(),
            component_version_id=component_version_id,
        )
        session.add(component)
        session.commit()

        node = db.GraphRunnerNode(
            node_id=component.id,
            graph_runner_id=prod_graph_id,
            node_type=db.NodeType.COMPONENT,
            is_start_node=False,
        )
        session.add(node)
        session.commit()

        with pytest.raises(ValueError, match="only draft versions"):
            delete_component_instance_service(
                session=session,
                graph_runner_id=prod_graph_id,
                component_instance_id=component.id,
            )

        delete_project_service(session=session, project_id=project_id)


def test_delete_fails_on_nonexistent_component():
    """Test that deletion fails if component doesn't exist"""
    with get_db_session() as session:
        project_id, graph_runner_id = create_project_and_graph_runner(
            session, project_name_prefix="delete_nonexistent_component_test", description="Test project"
        )

        nonexistent_component_id = uuid4()

        with pytest.raises(ValueError, match="not found"):
            delete_component_instance_service(
                session=session,
                graph_runner_id=graph_runner_id,
                component_instance_id=nonexistent_component_id,
            )

        delete_project_service(session=session, project_id=project_id)


def test_delete_fails_on_component_not_in_graph():
    """Test that deletion fails if component exists but is not in the specified graph"""
    with get_db_session() as session:
        project_id, graph_runner_id = create_project_and_graph_runner(
            session, project_name_prefix="delete_component_not_in_graph_test", description="Test project"
        )

        component_version_id = MOCK_UUIDS["component_version_1"]

        other_component = db.ComponentInstance(
            id=uuid4(),
            component_version_id=component_version_id,
        )
        session.add(other_component)
        session.commit()

        with pytest.raises(ValueError, match="is not in graph"):
            delete_component_instance_service(
                session=session,
                graph_runner_id=graph_runner_id,
                component_instance_id=other_component.id,
            )

        delete_project_service(session=session, project_id=project_id)


@pytest.mark.asyncio
async def test_component_level_and_graph_level_work_together():
    """Test that component-level saves work correctly with graph-level edge saves"""
    with get_db_session() as session:
        project_id, graph_runner_id = create_project_and_graph_runner(
            session, project_name_prefix="component_graph_integration_test", description="Test project"
        )

        component_version_id = MOCK_UUIDS["component_version_1"]
        component_id = MOCK_UUIDS["component_1"]

        component_1_id = uuid4()
        component_2_id = uuid4()

        for comp_id in [component_1_id, component_2_id]:
            component_data = ComponentInstanceUpdateSchema(
                id=comp_id,
                name=f"Component {comp_id}",
                ref=f"comp_{comp_id}",
                is_start_node=False,
                component_id=component_id,
                component_version_id=component_version_id,
                parameters=[],
                field_expressions=[],
                port_mappings=[],
            )

            with patch(MOCK_AGENT_SERVICE_PATH):
                await upsert_component_instance_service(
                    session=session,
                    graph_runner_id=graph_runner_id,
                    project_id=project_id,
                    component_data=component_data,
                    user_id=uuid4(),
                )

        graph_nodes = get_component_nodes(session, graph_runner_id)
        node_ids = [node.id for node in graph_nodes]
        assert component_1_id in node_ids
        assert component_2_id in node_ids

        delete_project_service(session=session, project_id=project_id)

import asyncio
from uuid import UUID, uuid4

from ada_backend.database.seed.utils import COMPONENT_UUIDS, COMPONENT_VERSION_UUIDS
from ada_backend.database.setup_db import get_db_session
from ada_backend.schemas.parameter_schema import PipelineParameterSchema
from ada_backend.schemas.pipeline.base import (
    ComponentInstanceSchema,
    ToolDescriptionSchema,
)
from ada_backend.schemas.pipeline.graph_schema import EdgeSchema, GraphUpdateSchema
from ada_backend.services.errors import GraphNotFound
from ada_backend.services.graph.delete_graph_service import delete_graph_runner_service
from ada_backend.services.graph.get_graph_service import get_graph_service
from ada_backend.services.graph.update_graph_service import update_graph_service
from ada_backend.services.project_service import delete_project_service
from tests.ada_backend.test_utils import create_project_and_graph_runner

COMPONENT_ID = COMPONENT_UUIDS["llm_call"]
COMPONENT_VERSION_ID = COMPONENT_VERSION_UUIDS["llm_call"]


def test_create_empty_graph_runner():
    """
    Create a empty graph runner.
    """
    with get_db_session() as session:
        # Create a unique project for this test to avoid constraint violations
        project_id, graph_runner_id = create_project_and_graph_runner(
            session=session,
            project_name_prefix="empty_graph_test",
            description="Test project for empty graph runner",
        )

        payload = GraphUpdateSchema(
            component_instances=[],
            relationships=[],
            edges=[],
        )

        response = asyncio.run(
            update_graph_service(
                session=session,
                graph_runner_id=graph_runner_id,
                project_id=project_id,
                graph_project=payload,
            )
        )

        assert response.graph_id == graph_runner_id

        results = get_graph_service(
            session=session,
            project_id=project_id,
            graph_runner_id=graph_runner_id,
        )

        # GET should include port_mappings; field expressions now nested per component instance
        assert results.port_mappings == []
        assert results.component_instances == []
        assert results.relationships == []
        assert results.edges == []

        # Cleanup
        delete_project_service(session, project_id)


def test_update_graph_runner():
    """
    Update the graph runner.
    """
    with get_db_session() as session:
        # Create a unique project for this test to avoid constraint violations
        project_id, graph_runner_id = create_project_and_graph_runner(
            session=session,
            project_name_prefix="update_graph_test",
            description="Test project for updating graph runner",
        )

        component_instance_1_id = uuid4()
        component_instance_2_id = uuid4()
        edge_id = uuid4()

        payload = GraphUpdateSchema(
            component_instances=[
                ComponentInstanceSchema(
                    id=component_instance_1_id,
                    name="LLM Call",
                    ref="",
                    is_start_node=True,
                    component_id=COMPONENT_ID,
                    component_version_id=COMPONENT_VERSION_ID,
                    parameters=[
                        PipelineParameterSchema(
                            value="Reformulate the question as a customer service query :\n{question}",
                            name="prompt_template",
                            order=None,
                        ),
                        PipelineParameterSchema(
                            value="openai:gpt-5-mini",
                            name="completion_model",
                            order=None,
                        ),
                    ],
                    tool_description=ToolDescriptionSchema(
                        name="Graph Test Chatbot",
                        description="Graph Test for Revaline",
                        tool_properties={},
                        required_tool_properties=[],
                    ),
                ),
                ComponentInstanceSchema(
                    id=component_instance_2_id,
                    name="Polite LLM",
                    ref="",
                    is_start_node=False,
                    component_id=COMPONENT_ID,
                    component_version_id=COMPONENT_VERSION_ID,
                    parameters=[
                        PipelineParameterSchema(
                            value="Add polite expressions to the question: {question} \n",
                            name="prompt_template",
                            order=None,
                        ),
                        PipelineParameterSchema(
                            value="openai:gpt-5-mini",
                            name="completion_model",
                            order=None,
                        ),
                    ],
                    tool_description=ToolDescriptionSchema(
                        name="Graph Test Chatbot",
                        description="Graph Test for Revaline",
                        tool_properties={},
                        required_tool_properties=[],
                    ),
                ),
            ],
            relationships=[],
            edges=[
                EdgeSchema(
                    id=edge_id,
                    origin=component_instance_1_id,
                    destination=component_instance_2_id,
                    order=1,
                ),
            ],
        )

        response = asyncio.run(
            update_graph_service(
                session=session,
                graph_runner_id=graph_runner_id,
                project_id=project_id,
                graph_project=payload,
            )
        )

        assert response.graph_id == graph_runner_id

        results = get_graph_service(
            session=session,
            project_id=project_id,
            graph_runner_id=graph_runner_id,
        )

        assert len(results.component_instances) == len(payload.component_instances)

        # Verify all expected IDs are present
        expected_ids = {ci.id for ci in payload.component_instances}
        actual_ids = {UUID(str(ci.id)) for ci in results.component_instances}
        assert actual_ids == expected_ids

        # Verify component IDs are correct
        expected_component_ids = {ci.component_id for ci in payload.component_instances}
        actual_component_ids = {ci.component_id for ci in results.component_instances}
        assert actual_component_ids == expected_component_ids
        assert len(results.relationships) == len(payload.relationships)
        assert len(results.edges) == len(payload.edges)

        # Cleanup
        delete_project_service(session, project_id)


def test_delete_graph_runner():
    with get_db_session() as session:
        # Create a unique project for this test to avoid constraint violations
        project_id, graph_runner_id = create_project_and_graph_runner(
            session=session,
            project_name_prefix="delete_graph_test",
            description="Test project for deleting graph runner",
        )

        # Verify the graph runner exists
        results = get_graph_service(
            session=session,
            project_id=project_id,
            graph_runner_id=graph_runner_id,
        )
        assert results is not None

        # Now delete it
        delete_graph_runner_service(session, graph_runner_id)

        # Verify it's gone - should raise GraphNotFound
        try:
            get_graph_service(
                session=session,
                project_id=project_id,
                graph_runner_id=graph_runner_id,
            )
            assert False, "Expected GraphNotFound exception"
        except GraphNotFound:
            pass  # Expected

        # Cleanup project
        delete_project_service(session, project_id)

from uuid import UUID, uuid4
import json

from ada_backend.database import models as db
from ada_backend.schemas.parameter_schema import PipelineParameterSchema
from ada_backend.schemas.pipeline.base import (
    ComponentRelationshipSchema,
    ComponentInstanceSchema,
    ToolDescriptionSchema,
)
from ada_backend.schemas.pipeline.graph_schema import EdgeSchema, GraphUpdateSchema, PortMappingSchema
from engine.agent.rag.rag import format_rag_tool_description
from ada_backend.database.seed.constants import COMPLETION_MODEL_IN_DB


GRAPH_TEST_TOOL_DESCRIPTION = ToolDescriptionSchema(
    name="Graph Test Chatbot",
    description="Graph Test for Revaline",
    tool_properties={},
    required_tool_properties=[],
)


def build_graph_test_source(source_id: UUID, organization_id: UUID) -> db.DataSource:
    source_record = db.DataSource(
        id=source_id,
        name="Test Source",
        type=db.SourceType.LOCAL,
        organization_id=organization_id,
        database_schema="test_schema",
        database_table_name="test_table",
        qdrant_collection_name="customer_service",
        qdrant_schema={
            "chunk_id_field": "chunk_id",
            "content_field": "content",
            "file_id_field": "file_id",
            "last_edited_ts_field": "last_edited_ts",
            "metadata_fields_to_keep": None,
        },
    )
    return source_record


def build_graph_test_chatbot(
    components: dict[str, UUID],
    graph_runner_id: UUID,
    source_id: UUID,
):
    agent_name = "graph_test_chatbot"
    COMPONENT_INSTANCES_IDS: dict[str, UUID] = {
        "synthesizer_instance": uuid4(),
        "retriever_instance": uuid4(),
        "rag_agent_instance": uuid4(),
        "llm_call_instance": uuid4(),
        "evaluation_instance": uuid4(),
    }

    rag_tool_description = format_rag_tool_description(source="customer_service")

    instances = [
        ComponentInstanceSchema(
            id=COMPONENT_INSTANCES_IDS["llm_call_instance"],
            name="LLM Call",
            component_id=components["llm_call"],
            version_id=components["llm_call"],
            ref=f"{agent_name}_llm_call_instance",
            is_start_node=True,
            parameters=[
                PipelineParameterSchema(
                    name="prompt_template",
                    value="Reformulate the question as a customer service query :\n{input}",
                ),
                PipelineParameterSchema(name=COMPLETION_MODEL_IN_DB, value="openai:gpt-4o-mini"),
            ],
            tool_description=GRAPH_TEST_TOOL_DESCRIPTION,
        ),
        ComponentInstanceSchema(
            id=COMPONENT_INSTANCES_IDS["rag_agent_instance"],
            name="RAG",
            component_id=components["rag_agent"],
            version_id=components["rag_agent"],
            ref=f"{agent_name}_rag_agent_instance",
            parameters=[],
            tool_description=ToolDescriptionSchema(
                name=rag_tool_description.name,
                description=rag_tool_description.description,
                tool_properties=rag_tool_description.tool_properties,
                required_tool_properties=rag_tool_description.required_tool_properties,
            ),
        ),
        ComponentInstanceSchema(
            id=COMPONENT_INSTANCES_IDS["synthesizer_instance"],
            component_id=components["synthesizer"],
            version_id=components["synthesizer"],
            name="Synthesizer",
            ref=f"{agent_name}_synthesizer_instance",
            parameters=[
                PipelineParameterSchema(name=COMPLETION_MODEL_IN_DB, value="openai:gpt-4o-mini"),
            ],
        ),
        # Retriever
        ComponentInstanceSchema(
            id=COMPONENT_INSTANCES_IDS["retriever_instance"],
            component_id=components["retriever"],
            version_id=components["retriever"],
            name="Retriever",
            ref=f"{agent_name}_retriever_instance",
            parameters=[
                PipelineParameterSchema(name="max_retrieved_chunks", value=10),
                PipelineParameterSchema(
                    name="data_source", value=json.dumps({"id": str(source_id), "name": "Test Source"})
                ),
            ],
        ),
        ComponentInstanceSchema(
            id=COMPONENT_INSTANCES_IDS["evaluation_instance"],
            name="Evaluation",
            component_id=components["llm_call"],
            version_id=components["llm_call"],
            ref=f"{agent_name}_evaluation_instance",
            parameters=[
                PipelineParameterSchema(
                    name="prompt_template",
                    value="Evaluate the pertinence of the following answer:\n{input}",
                ),
                PipelineParameterSchema(name=COMPLETION_MODEL_IN_DB, value="openai:gpt-4o-mini"),
            ],
            tool_description=GRAPH_TEST_TOOL_DESCRIPTION,
        ),
    ]

    relations = [
        ComponentRelationshipSchema(
            parent_component_instance_id=COMPONENT_INSTANCES_IDS["rag_agent_instance"],
            child_component_instance_id=COMPONENT_INSTANCES_IDS["retriever_instance"],
            parameter_name="retriever",
        ),
        ComponentRelationshipSchema(
            parent_component_instance_id=COMPONENT_INSTANCES_IDS["rag_agent_instance"],
            child_component_instance_id=COMPONENT_INSTANCES_IDS["synthesizer_instance"],
            parameter_name="synthesizer",
        ),
    ]

    edges = [
        EdgeSchema(
            id=uuid4(),
            origin=COMPONENT_INSTANCES_IDS["llm_call_instance"],
            destination=COMPONENT_INSTANCES_IDS["rag_agent_instance"],
        ),
        EdgeSchema(
            id=uuid4(),
            origin=COMPONENT_INSTANCES_IDS["rag_agent_instance"],
            destination=COMPONENT_INSTANCES_IDS["evaluation_instance"],
            order=2,
        ),
        EdgeSchema(
            id=uuid4(),
            origin=COMPONENT_INSTANCES_IDS["llm_call_instance"],
            destination=COMPONENT_INSTANCES_IDS["evaluation_instance"],
            order=1,
        ),
    ]
    port_mappings = [
        PortMappingSchema(
            source_instance_id=COMPONENT_INSTANCES_IDS["llm_call_instance"],
            source_port_name="output",
            target_instance_id=COMPONENT_INSTANCES_IDS["rag_agent_instance"],
            target_port_name="query_text",
        ),
        PortMappingSchema(
            source_instance_id=COMPONENT_INSTANCES_IDS["rag_agent_instance"],
            source_port_name="output",
            target_instance_id=COMPONENT_INSTANCES_IDS["evaluation_instance"],
            target_port_name="messages",
        ),
        PortMappingSchema(
            source_instance_id=COMPONENT_INSTANCES_IDS["llm_call_instance"],
            source_port_name="output",
            target_instance_id=COMPONENT_INSTANCES_IDS["evaluation_instance"],
            target_port_name="messages",
        ),
    ]
    return GraphUpdateSchema(
        component_instances=instances, relationships=relations, edges=edges, port_mappings=port_mappings
    )

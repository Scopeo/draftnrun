"""
E2E test for field expressions functionality.
Tests the complete flow from field expression parsing to GraphRunner execution.
"""

import asyncio
from uuid import UUID, uuid4

import pytest

from ada_backend.database.models import EnvType
from ada_backend.database.seed.utils import COMPONENT_UUIDS
from ada_backend.database.setup_db import get_db_session
from ada_backend.schemas.parameter_schema import ParameterKind
from ada_backend.schemas.pipeline.graph_schema import GraphUpdateSchema
from ada_backend.schemas.project_schema import ProjectCreateSchema
from ada_backend.services.graph.deploy_graph_service import deploy_graph_service
from ada_backend.services.graph.get_graph_service import get_graph_service
from ada_backend.services.graph.load_copy_graph_service import load_copy_graph_service
from ada_backend.services.graph.update_graph_service import update_graph_service
from ada_backend.services.project_service import create_workflow, delete_project_service, get_project_service
from engine.field_expressions.errors import FieldExpressionError

# Test constants
ORGANIZATION_ID = UUID("37b7d67f-8f29-4fce-8085-19dea582f605")  # umbrella organization
COMPONENT_ID = str(COMPONENT_UUIDS["llm_call"])
COMPONENT_VERSION_ID = str(COMPONENT_UUIDS["llm_call"])


def _run_update_graph(session, graph_runner_id: UUID, project_id: UUID, payload: dict):
    """Helper to run async update_graph_service synchronously."""
    graph_update = GraphUpdateSchema(**payload)

    async def _update():
        return await update_graph_service(
            session=session,
            graph_runner_id=graph_runner_id,
            project_id=project_id,
            graph_project=graph_update,
            env=EnvType.DRAFT,
        )

    return asyncio.run(_update())


def _get_field_expressions_from_instance(instance: dict) -> list[dict]:
    """
    Helper to get field_expressions from a component instance.
    Reads ONLY from parameters[kind="input"] (new unified format).
    Returns list with field_name and expression_text.
    """
    input_params = [p for p in instance.get("parameters", []) if p.get("kind") == ParameterKind.INPUT]

    field_expressions = []
    for param in input_params:
        if param.get("value"):
            field_expressions.append({
                "field_name": param["name"],
                "expression_text": str(param["value"]),
            })

    return field_expressions


def _create_component_instance(
    instance_id: str,
    name: str,
    is_start_node: bool,
    prompt_template_value: str,
    input_expression: dict | None = None,
) -> dict:
    params = [
        {"value": prompt_template_value, "name": "prompt_template", "order": None},
        {"value": "openai:gpt-4o-mini", "name": "completion_model", "order": None},
        {"value": 0.2, "name": "default_temperature", "order": None},
    ]

    if input_expression:
        params.append({
            "name": input_expression["field_name"],
            "value": input_expression["expression_text"],
            "kind": ParameterKind.INPUT,
            "order": None,
        })

    instance = {
        "is_agent": True,
        "is_protected": False,
        "function_callable": True,
        "can_use_function_calling": False,
        "tool_parameter_name": None,
        "subcomponents_info": [],
        "id": instance_id,
        "name": name,
        "ref": "",
        "is_start_node": is_start_node,
        "component_id": COMPONENT_ID,
        "component_version_id": COMPONENT_VERSION_ID,
        "parameters": params,
        "tool_description": {
            "name": "Test Tool",
            "description": "d",
            "tool_properties": {},
            "required_tool_properties": [],
        },
        "component_name": "LLM Call",
        "component_description": "Templated LLM Call",
    }
    return instance


def _create_graph_payload_with_field_expressions(
    src_instance_id: str,
    dst_instance_id: str,
    edge_id: str,
    expression_text: str,
) -> dict:
    return {
        "component_instances": [
            _create_component_instance(
                instance_id=src_instance_id,
                name="Source Agent",
                is_start_node=True,
                prompt_template_value="Hello",
            ),
            _create_component_instance(
                instance_id=dst_instance_id,
                name="Target Agent",
                is_start_node=False,
                prompt_template_value="Process: {input}",
                input_expression={"field_name": "messages", "expression_text": expression_text},
            ),
        ],
        "relationships": [],
        "edges": [{"id": edge_id, "origin": src_instance_id, "destination": dst_instance_id, "order": 0}],
    }


def _create_project_and_get_graph_runner(session, project_name_prefix: str) -> tuple[UUID, UUID]:
    """Create a test project and return project_id and draft graph_runner_id."""
    project_id = uuid4()
    user_id = uuid4()

    project_payload = ProjectCreateSchema(
        project_id=project_id,
        project_name=f"{project_name_prefix}_{project_id}",
        description=f"Test {project_name_prefix}",
    )

    create_workflow(
        session=session,
        user_id=user_id,
        organization_id=ORGANIZATION_ID,
        project_schema=project_payload,
    )

    project_details = get_project_service(session, project_id)
    draft_graph_runner_id = next(gr.graph_runner_id for gr in project_details.graph_runners if gr.env == EnvType.DRAFT)

    return project_id, draft_graph_runner_id


def _assert_expression_remapped(
    expr_json: dict,
    expr_text: str,
    original_instance_id: str,
    new_instance_id: str,
    context: str = "",
) -> None:
    """Assert that expression has been remapped from original_instance_id to new_instance_id."""
    assert str(original_instance_id) not in expr_text, (
        f"{context}Old instance ID {original_instance_id} should not be in expression"
    )
    assert str(new_instance_id) in expr_text, f"{context}New instance ID {new_instance_id} should be in expression"

    if expr_json["type"] == "ref":
        assert expr_json["instance"] == str(new_instance_id), (
            f"{context}Ref should use new instance ID {new_instance_id}, got {expr_json['instance']}"
        )
        assert expr_json["instance"] != str(original_instance_id), (
            f"{context}Ref should not use old instance ID {original_instance_id}"
        )
    elif expr_json["type"] == "concat":
        for part in expr_json["parts"]:
            if part["type"] == "ref":
                assert part["instance"] == str(new_instance_id), (
                    f"{context}Ref part should use new instance ID {new_instance_id}, got {part['instance']}"
                )
                assert part["instance"] != str(original_instance_id), (
                    f"{context}Ref part should not use old instance ID {original_instance_id}"
                )


def test_field_expressions_e2e():
    """Test field expressions parsing and GraphRunner integration end-to-end."""
    with get_db_session() as session:
        project_id, graph_runner_id = _create_project_and_get_graph_runner(session, "field_expressions_test")

        src_instance_id = str(uuid4())
        dst_instance_id = str(uuid4())
        edge_id = str(uuid4())

        expression_text = f"Task: @{{{{{src_instance_id}.output}}}} - Style: @{{{{{src_instance_id}.output}}}}"

        payload = {
            "component_instances": [
                {
                    "is_agent": True,
                    "is_protected": False,
                    "function_callable": True,
                    "can_use_function_calling": False,
                    "tool_parameter_name": None,
                    "subcomponents_info": [],
                    "id": src_instance_id,
                    "name": "Source Agent",
                    "ref": "",
                    "is_start_node": True,
                    "component_id": COMPONENT_ID,
                    "component_version_id": COMPONENT_VERSION_ID,
                    "parameters": [
                        {
                            "value": "Hello world",
                            "name": "prompt_template",
                            "order": None,
                            "type": "string",
                            "nullable": False,
                            "default": "Answer this question: {input}",
                            "ui_component": "Textarea",
                            "ui_component_properties": {},
                            "is_advanced": False,
                        },
                        {
                            "value": "openai:gpt-4o-mini",
                            "name": "completion_model",
                            "order": None,
                            "type": "string",
                            "nullable": False,
                            "default": "openai:gpt-4o-mini",
                            "ui_component": "Select",
                            "ui_component_properties": {},
                            "is_advanced": False,
                        },
                    ],
                    "tool_description": {
                        "name": "Test Tool",
                        "description": "Test Description",
                        "tool_properties": {},
                        "required_tool_properties": [],
                    },
                    "component_name": "LLM Call",
                    "component_description": "Templated LLM Call",
                },
                {
                    "is_agent": True,
                    "is_protected": False,
                    "function_callable": True,
                    "can_use_function_calling": False,
                    "tool_parameter_name": None,
                    "subcomponents_info": [],
                    "id": dst_instance_id,
                    "name": "Target Agent",
                    "ref": "",
                    "is_start_node": False,
                    "component_id": COMPONENT_ID,
                    "component_version_id": COMPONENT_VERSION_ID,
                    "tool_description": {
                        "name": "Test Tool",
                        "description": "Test Description",
                        "tool_properties": {},
                        "required_tool_properties": [],
                    },
                    "component_name": "LLM Call",
                    "component_description": "Templated LLM Call",
                    "parameters": [
                        {
                            "value": "Process this: {input}",
                            "name": "prompt_template",
                            "order": None,
                            "type": "string",
                            "nullable": False,
                            "default": "Answer this question: {input}",
                            "ui_component": "Textarea",
                            "ui_component_properties": {},
                            "is_advanced": False,
                        },
                        {
                            "value": "openai:gpt-4o-mini",
                            "name": "completion_model",
                            "order": None,
                            "type": "string",
                            "nullable": False,
                            "default": "openai:gpt-4o-mini",
                            "ui_component": "Select",
                            "ui_component_properties": {},
                            "is_advanced": False,
                        },
                        {
                            "name": "messages",
                            "value": expression_text,
                            "kind": ParameterKind.INPUT,
                            "order": None,
                        },
                    ],
                },
            ],
            "relationships": [],
            "edges": [
                {
                    "id": edge_id,
                    "origin": src_instance_id,
                    "destination": dst_instance_id,
                    "order": 0,
                }
            ],
        }

        _run_update_graph(session, graph_runner_id, project_id, payload)

        graph_data = get_graph_service(
            session=session,
            project_id=project_id,
            graph_runner_id=graph_runner_id,
        )

        assert graph_data.component_instances is not None
        assert len(graph_data.component_instances) == 2

        assert graph_data.edges is not None
        assert len(graph_data.edges) == 1
        assert str(graph_data.edges[0].origin) == src_instance_id
        assert str(graph_data.edges[0].destination) == dst_instance_id

        dst = next(ci for ci in graph_data.component_instances if str(ci.id) == dst_instance_id)
        field_expressions = _get_field_expressions_from_instance(dst.model_dump())
        assert len(field_expressions) == 1
        stored_expression = field_expressions[0]
        assert stored_expression["field_name"] == "messages"

        assert dst.field_expressions is not None
        assert len(dst.field_expressions) == 1
        expression_json = dst.field_expressions[0].expression_json
        assert expression_json is not None

        assert expression_json["type"] == "concat"
        assert "parts" in expression_json
        assert len(expression_json["parts"]) == 4  # "Task: ", ref, " - Style: ", ref

        parts = expression_json["parts"]
        assert parts[0]["type"] == "literal"
        assert parts[0]["value"] == "Task: "
        assert parts[1]["type"] == "ref"
        assert parts[1]["instance"] == src_instance_id
        assert parts[1]["port"] == "output"
        assert parts[2]["type"] == "literal"
        assert parts[2]["value"] == " - Style: "
        assert parts[3]["type"] == "ref"
        assert parts[3]["instance"] == str(src_instance_id)
        assert parts[3]["port"] == "output"

        delete_project_service(session, project_id)


def test_invalid_reference_uuid_returns_error():
    """Test that invalid UUID in reference raises FieldExpressionError."""
    with get_db_session() as session:
        project_id, graph_runner_id = _create_project_and_get_graph_runner(session, "field_expr_invalid_uuid")

        src_instance_id = str(uuid4())
        dst_instance_id = str(uuid4())
        edge_id = str(uuid4())

        bad_instance_id = "not-a-uuid"
        expression_text = f"@{{{{{bad_instance_id}.output}}}}"

        payload = {
            "component_instances": [
                {
                    "is_agent": True,
                    "is_protected": False,
                    "function_callable": True,
                    "can_use_function_calling": False,
                    "tool_parameter_name": None,
                    "subcomponents_info": [],
                    "id": src_instance_id,
                    "name": "Source Agent",
                    "ref": "",
                    "is_start_node": True,
                    "component_id": COMPONENT_ID,
                    "component_version_id": COMPONENT_VERSION_ID,
                    "parameters": [],
                    "tool_description": {
                        "name": "Test Tool",
                        "description": "d",
                        "tool_properties": {},
                        "required_tool_properties": [],
                    },
                    "component_name": "LLM Call",
                    "component_description": "Templated LLM Call",
                },
                {
                    "is_agent": True,
                    "is_protected": False,
                    "function_callable": True,
                    "can_use_function_calling": False,
                    "tool_parameter_name": None,
                    "subcomponents_info": [],
                    "id": dst_instance_id,
                    "name": "Target Agent",
                    "ref": "",
                    "is_start_node": False,
                    "component_id": COMPONENT_ID,
                    "component_version_id": COMPONENT_VERSION_ID,
                    "tool_description": {
                        "name": "Test Tool",
                        "description": "d",
                        "tool_properties": {},
                        "required_tool_properties": [],
                    },
                    "component_name": "LLM Call",
                    "component_description": "Templated LLM Call",
                    "parameters": [
                        {
                            "name": "prompt_template",
                            "value": expression_text,
                            "kind": ParameterKind.INPUT,
                            "order": None,
                        }
                    ],
                },
            ],
            "relationships": [],
            "edges": [{"id": edge_id, "origin": src_instance_id, "destination": dst_instance_id, "order": 0}],
        }

        with pytest.raises(FieldExpressionError):
            _run_update_graph(session, graph_runner_id, project_id, payload)

        delete_project_service(session, project_id)


def test_deploy_remaps_field_expression_instance_ids():
    """Deploy should remap instance IDs in field expressions to new IDs."""
    with get_db_session() as session:
        project_id, graph_runner_id = _create_project_and_get_graph_runner(session, "deploy_expr")

        src_instance_id = str(uuid4())
        dst_instance_id = str(uuid4())
        edge_id = str(uuid4())
        expression_text = (
            f"Task: @{{{{{src_instance_id}.output}}}} - Sources: @{{{{{src_instance_id}.artifacts::docs}}}}"
        )

        payload = _create_graph_payload_with_field_expressions(
            src_instance_id=src_instance_id,
            dst_instance_id=dst_instance_id,
            edge_id=edge_id,
            expression_text=expression_text,
        )

        _run_update_graph(session, graph_runner_id, project_id, payload)

        deploy_data = deploy_graph_service(
            session=session,
            graph_runner_id=graph_runner_id,
            project_id=project_id,
        )
        new_draft_graph_runner_id = deploy_data.draft_graph_runner_id

        new_graph = get_graph_service(
            session=session,
            project_id=project_id,
            graph_runner_id=new_draft_graph_runner_id,
        )

        target_instance = next(ci for ci in new_graph.component_instances if ci.name == "Target Agent")
        field_expressions = _get_field_expressions_from_instance(target_instance.model_dump())
        assert len(field_expressions) == 1

        expr_text = field_expressions[0]["expression_text"]
        assert target_instance.field_expressions is not None
        assert len(target_instance.field_expressions) == 1
        expr_json = target_instance.field_expressions[0].expression_json
        assert expr_json is not None

        src_instance_new = next(ci for ci in new_graph.component_instances if ci.name == "Source Agent")
        new_src_id = src_instance_new.id

        _assert_expression_remapped(expr_json, expr_text, src_instance_id, new_src_id)

        delete_project_service(session, project_id)


def test_load_copy_includes_field_expressions_and_roundtrip():
    """load-copy should include field expressions and remap refs to new IDs, and its payload should PUT cleanly."""
    with get_db_session() as session:
        project_id, graph_runner_id = _create_project_and_get_graph_runner(session, "load_copy_expr")

        src_instance_id = str(uuid4())
        dst_instance_id = str(uuid4())
        edge_id = str(uuid4())
        expression_text = f"Task: @{{{{{src_instance_id}.output}}}} - Style: @{{{{{src_instance_id}.output}}}}"

        payload = _create_graph_payload_with_field_expressions(
            src_instance_id=src_instance_id,
            dst_instance_id=dst_instance_id,
            edge_id=edge_id,
            expression_text=expression_text,
        )

        _run_update_graph(session, graph_runner_id, project_id, payload)

        load_payload = load_copy_graph_service(
            session=session,
            project_id_to_copy=project_id,
            graph_runner_id_to_copy=graph_runner_id,
        )

        assert len(load_payload.component_instances) == 2
        new_src = next(ci for ci in load_payload.component_instances if ci.name == "Source Agent")
        new_dst = next(ci for ci in load_payload.component_instances if ci.name == "Target Agent")
        assert new_src.id != src_instance_id
        assert new_dst.id != dst_instance_id

        field_expressions = _get_field_expressions_from_instance(new_dst.model_dump())
        assert len(field_expressions) == 1
        expr_text_new = field_expressions[0]["expression_text"]
        assert str(src_instance_id) not in expr_text_new
        assert str(new_src.id) in expr_text_new

        project_id_2, clone_graph_runner_id = _create_project_and_get_graph_runner(session, "load_copy_expr_target")
        _run_update_graph(session, clone_graph_runner_id, project_id_2, load_payload.model_dump())

        cloned = get_graph_service(
            session=session,
            project_id=project_id_2,
            graph_runner_id=clone_graph_runner_id,
        )
        cloned_dst = next(ci for ci in cloned.component_instances if ci.name == "Target Agent")
        field_expressions = _get_field_expressions_from_instance(cloned_dst.model_dump())
        assert len(field_expressions) == 1

        delete_project_service(session, project_id)
        delete_project_service(session, project_id_2)


def test_load_copy_cloned_graph_has_remapped_field_expressions():
    """After PUT load-copy payload, the cloned graph should have field expressions with remapped IDs."""
    with get_db_session() as session:
        project_id, graph_runner_id = _create_project_and_get_graph_runner(session, "load_copy_clone")

        src_instance_id = str(uuid4())
        dst_instance_id = str(uuid4())
        edge_id = str(uuid4())
        expression_text = (
            f"Task: @{{{{{src_instance_id}.output}}}} - Sources: @{{{{{src_instance_id}.artifacts::docs}}}}"
        )

        payload = _create_graph_payload_with_field_expressions(
            src_instance_id=src_instance_id,
            dst_instance_id=dst_instance_id,
            edge_id=edge_id,
            expression_text=expression_text,
        )

        _run_update_graph(session, graph_runner_id, project_id, payload)

        load_payload = load_copy_graph_service(
            session=session,
            project_id_to_copy=project_id,
            graph_runner_id_to_copy=graph_runner_id,
        )

        project_id_clone, clone_graph_runner_id = _create_project_and_get_graph_runner(
            session, "load_copy_clone_target"
        )
        _run_update_graph(session, clone_graph_runner_id, project_id_clone, load_payload.model_dump())

        cloned_graph = get_graph_service(
            session=session,
            project_id=project_id_clone,
            graph_runner_id=clone_graph_runner_id,
        )

        cloned_src = next(ci for ci in cloned_graph.component_instances if ci.name == "Source Agent")
        cloned_dst = next(ci for ci in cloned_graph.component_instances if ci.name == "Target Agent")
        cloned_src_id = cloned_src.id

        field_expressions = _get_field_expressions_from_instance(cloned_dst.model_dump())
        assert len(field_expressions) == 1

        cloned_expr_text = field_expressions[0]["expression_text"]
        assert cloned_dst.field_expressions is not None
        assert len(cloned_dst.field_expressions) == 1
        cloned_expr_json = cloned_dst.field_expressions[0].expression_json
        assert cloned_expr_json is not None

        _assert_expression_remapped(
            cloned_expr_json, cloned_expr_text, src_instance_id, cloned_src_id, context="Cloned graph: "
        )

        delete_project_service(session, project_id)
        delete_project_service(session, project_id_clone)


def test_invalid_reference_unknown_port_returns_error():
    """Test that invalid port in reference raises FieldExpressionError."""
    with get_db_session() as session:
        project_id, graph_runner_id = _create_project_and_get_graph_runner(session, "field_expr_invalid_port")

        src_instance_id = str(uuid4())
        dst_instance_id = str(uuid4())
        edge_id = str(uuid4())

        expression_text = f"@{{{{{src_instance_id}.unknown_port}}}}"

        payload = {
            "component_instances": [
                {
                    "is_agent": True,
                    "is_protected": False,
                    "function_callable": True,
                    "can_use_function_calling": False,
                    "tool_parameter_name": None,
                    "subcomponents_info": [],
                    "id": src_instance_id,
                    "name": "Source Agent",
                    "ref": "",
                    "is_start_node": True,
                    "component_id": COMPONENT_ID,
                    "component_version_id": COMPONENT_VERSION_ID,
                    "parameters": [],
                    "tool_description": {
                        "name": "Test Tool",
                        "description": "d",
                        "tool_properties": {},
                        "required_tool_properties": [],
                    },
                    "component_name": "LLM Call",
                    "component_description": "Templated LLM Call",
                },
                {
                    "is_agent": True,
                    "is_protected": False,
                    "function_callable": True,
                    "can_use_function_calling": False,
                    "tool_parameter_name": None,
                    "subcomponents_info": [],
                    "id": dst_instance_id,
                    "name": "Target Agent",
                    "ref": "",
                    "is_start_node": False,
                    "component_id": COMPONENT_ID,
                    "component_version_id": COMPONENT_VERSION_ID,
                    "tool_description": {
                        "name": "Test Tool",
                        "description": "d",
                        "tool_properties": {},
                        "required_tool_properties": [],
                    },
                    "component_name": "LLM Call",
                    "component_description": "Templated LLM Call",
                    "parameters": [
                        {
                            "name": "prompt_template",
                            "value": expression_text,
                            "kind": ParameterKind.INPUT,
                            "order": None,
                        }
                    ],
                },
            ],
            "relationships": [],
            "edges": [{"id": edge_id, "origin": src_instance_id, "destination": dst_instance_id, "order": 0}],
        }

        with pytest.raises(FieldExpressionError):
            _run_update_graph(session, graph_runner_id, project_id, payload)

        delete_project_service(session, project_id)

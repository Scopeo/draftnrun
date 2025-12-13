import uuid
from types import SimpleNamespace

from ada_backend.services.pipeline import update_pipeline_service
from ada_backend.schemas.pipeline.base import ComponentInstanceSchema
from ada_backend.schemas.parameter_schema import PipelineParameterSchema, ParameterKind
from ada_backend.database import models as db


def test_create_or_update_component_instance_ignores_input_kind_parameters(monkeypatch):
    session = object()

    component_id = uuid.uuid4()
    component_version_id = uuid.uuid4()
    instance_id = uuid.uuid4()
    param_def_id = uuid.uuid4()

    instance = ComponentInstanceSchema(
        id=instance_id,
        name="MCP Client Tool",
        ref="mcp",
        is_start_node=False,
        component_id=component_id,
        component_version_id=component_version_id,
        parameters=[
            PipelineParameterSchema(name="input", value="{messages}", kind=ParameterKind.INPUT),
            PipelineParameterSchema(name="server_command", value="uvx"),
        ],
        tool_description=None,
        integration=None,
    )

    monkeypatch.setattr(
        update_pipeline_service,
        "get_component_by_id",
        lambda *_args, **_kwargs: SimpleNamespace(name="MCP Client Tool"),
    )
    monkeypatch.setattr(
        update_pipeline_service,
        "upsert_component_instance",
        lambda *_args, **_kwargs: SimpleNamespace(id=instance_id),
    )
    monkeypatch.setattr(
        update_pipeline_service, "delete_component_instance_parameters", lambda *_args, **_kwargs: None
    )

    param_def = SimpleNamespace(
        id=param_def_id,
        name="server_command",
        type=db.ParameterType.STRING,
        nullable=False,
    )
    monkeypatch.setattr(
        update_pipeline_service,
        "get_component_parameter_definition_by_component_version",
        lambda *_args, **_kwargs: [param_def],
    )
    monkeypatch.setattr(
        update_pipeline_service,
        "get_port_definitions_for_component_version_ids",
        lambda *_args, **_kwargs: [],
    )

    calls: list[dict] = []

    def fake_upsert_basic_parameter(*_args, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(update_pipeline_service, "upsert_basic_parameter", fake_upsert_basic_parameter)

    created_id = update_pipeline_service.create_or_update_component_instance(session, instance, uuid.uuid4())
    assert created_id == instance_id

    assert len(calls) == 1
    assert calls[0]["parameter_definition_id"] == param_def_id
    assert calls[0]["value"] == "uvx"


def test_create_or_update_component_instance_skips_input_port_params_even_without_kind(monkeypatch):
    session = object()

    component_id = uuid.uuid4()
    component_version_id = uuid.uuid4()
    instance_id = uuid.uuid4()
    param_def_id = uuid.uuid4()

    instance = ComponentInstanceSchema(
        id=instance_id,
        name="MCP Client Tool",
        ref="mcp",
        is_start_node=False,
        component_id=component_id,
        component_version_id=component_version_id,
        parameters=[
            PipelineParameterSchema(name="input", value="{messages}"),
            PipelineParameterSchema(name="server_command", value="uvx"),
        ],
        tool_description=None,
        integration=None,
    )

    monkeypatch.setattr(
        update_pipeline_service,
        "get_component_by_id",
        lambda *_args, **_kwargs: SimpleNamespace(name="MCP Client Tool"),
    )
    monkeypatch.setattr(
        update_pipeline_service,
        "upsert_component_instance",
        lambda *_args, **_kwargs: SimpleNamespace(id=instance_id),
    )
    monkeypatch.setattr(
        update_pipeline_service, "delete_component_instance_parameters", lambda *_args, **_kwargs: None
    )

    param_def = SimpleNamespace(
        id=param_def_id,
        name="server_command",
        type=db.ParameterType.STRING,
        nullable=False,
    )
    monkeypatch.setattr(
        update_pipeline_service,
        "get_component_parameter_definition_by_component_version",
        lambda *_args, **_kwargs: [param_def],
    )

    port_def = SimpleNamespace(name="input", port_type=db.PortType.INPUT)
    monkeypatch.setattr(
        update_pipeline_service,
        "get_port_definitions_for_component_version_ids",
        lambda *_args, **_kwargs: [port_def],
    )

    calls: list[dict] = []

    def fake_upsert_basic_parameter(*_args, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(update_pipeline_service, "upsert_basic_parameter", fake_upsert_basic_parameter)

    created_id = update_pipeline_service.create_or_update_component_instance(session, instance, uuid.uuid4())
    assert created_id == instance_id

    assert len(calls) == 1
    assert calls[0]["parameter_definition_id"] == param_def_id
    assert calls[0]["value"] == "uvx"

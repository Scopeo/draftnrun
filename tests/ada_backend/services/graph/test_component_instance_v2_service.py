from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from ada_backend.schemas.parameter_schema import PipelineParameterV2Schema
from ada_backend.schemas.pipeline.graph_schema import ComponentCreateV2Schema, ComponentUpdateV2Schema
from ada_backend.services.graph.component_instance_v2_service import (
    _split_unified_parameters,
    create_component_in_graph,
    delete_component_from_graph,
    update_single_component,
)


@pytest.fixture
def session():
    return MagicMock()


@pytest.fixture
def ids():
    return {
        "graph_runner_id": uuid4(),
        "project_id": uuid4(),
        "component_id": uuid4(),
        "component_version_id": uuid4(),
        "instance_id": uuid4(),
    }


class TestCreateComponentInGraph:
    @patch("ada_backend.services.graph.component_instance_v2_service.upsert_component_node")
    @patch("ada_backend.services.graph.component_instance_v2_service.create_or_update_component_instance")
    def test_creates_instance_and_node(self, mock_create, mock_upsert_node, session, ids):
        created_id = uuid4()
        mock_create.return_value = created_id

        payload = ComponentCreateV2Schema(
            component_id=ids["component_id"],
            component_version_id=ids["component_version_id"],
            label="My LLM",
            is_start_node=False,
            parameters=[{"name": "prompt", "value": "hello"}],
        )

        result = create_component_in_graph(session, ids["graph_runner_id"], ids["project_id"], payload)

        assert result == created_id
        mock_create.assert_called_once()
        instance_schema = mock_create.call_args[0][1]
        assert instance_schema.name == "My LLM"
        assert instance_schema.component_id == ids["component_id"]

        mock_upsert_node.assert_called_once_with(
            session,
            graph_runner_id=ids["graph_runner_id"],
            component_instance_id=created_id,
            is_start_node=False,
        )


class TestUpdateSingleComponent:
    @patch("ada_backend.services.graph.component_instance_v2_service.upsert_component_node")
    @patch("ada_backend.services.graph.component_instance_v2_service.create_or_update_component_instance")
    @patch("ada_backend.services.graph.component_instance_v2_service.get_component_nodes")
    @patch("ada_backend.services.graph.component_instance_v2_service.get_component_instance_by_id")
    def test_updates_existing_instance(
        self, mock_get_inst, mock_get_nodes, mock_create, mock_upsert_node, session, ids
    ):
        mock_instance = MagicMock()
        mock_instance.name = "Old Name"
        mock_instance.component_version_id = ids["component_version_id"]
        mock_instance.component_version.component_id = ids["component_id"]
        mock_get_inst.return_value = mock_instance

        node = MagicMock()
        node.id = ids["instance_id"]
        node.is_start_node = False
        mock_get_nodes.return_value = [node]

        payload = ComponentUpdateV2Schema(
            parameters=[{"name": "prompt", "value": "updated"}],
            label="New Name",
        )

        update_single_component(session, ids["graph_runner_id"], ids["project_id"], ids["instance_id"], payload)

        mock_create.assert_called_once()
        instance_schema = mock_create.call_args[0][1]
        assert instance_schema.id == ids["instance_id"]
        assert instance_schema.name == "New Name"

    @patch("ada_backend.services.graph.component_instance_v2_service.get_component_nodes")
    @patch("ada_backend.services.graph.component_instance_v2_service.get_component_instance_by_id")
    def test_raises_if_not_in_graph(self, mock_get_inst, mock_get_nodes, session, ids):
        mock_get_inst.return_value = MagicMock()
        mock_get_nodes.return_value = []

        payload = ComponentUpdateV2Schema(parameters=[])
        with pytest.raises(ValueError, match="does not belong to graph"):
            update_single_component(session, ids["graph_runner_id"], ids["project_id"], ids["instance_id"], payload)

    @patch("ada_backend.services.graph.component_instance_v2_service.get_component_nodes")
    @patch("ada_backend.services.graph.component_instance_v2_service.get_component_instance_by_id")
    def test_raises_if_instance_not_found(self, mock_get_inst, mock_get_nodes, session, ids):
        mock_get_inst.return_value = None

        payload = ComponentUpdateV2Schema(parameters=[])
        with pytest.raises(ValueError, match="not found"):
            update_single_component(session, ids["graph_runner_id"], ids["project_id"], ids["instance_id"], payload)


class TestDeleteComponentFromGraph:
    @patch("ada_backend.services.graph.component_instance_v2_service.delete_node")
    @patch("ada_backend.services.graph.component_instance_v2_service.delete_component_instances_from_nodes")
    @patch("ada_backend.services.graph.component_instance_v2_service.get_edges")
    @patch("ada_backend.services.graph.component_instance_v2_service.get_component_nodes")
    def test_deletes_instance_and_cascades(
        self, mock_get_nodes, mock_get_edges, mock_del_inst, mock_del_node, session, ids
    ):
        node = MagicMock()
        node.id = ids["instance_id"]
        mock_get_nodes.return_value = [node]
        mock_get_edges.return_value = []
        session.query.return_value.filter.return_value.all.return_value = []

        delete_component_from_graph(session, ids["graph_runner_id"], ids["instance_id"])

        mock_del_inst.assert_called_once_with(session, {ids["instance_id"]})
        mock_del_node.assert_called_once_with(session, ids["instance_id"])

    @patch("ada_backend.services.graph.component_instance_v2_service.get_component_nodes")
    def test_raises_if_not_in_graph(self, mock_get_nodes, session, ids):
        mock_get_nodes.return_value = []

        with pytest.raises(ValueError, match="does not belong to graph"):
            delete_component_from_graph(session, ids["graph_runner_id"], ids["instance_id"])

    @patch("ada_backend.services.graph.component_instance_v2_service.delete_node")
    @patch("ada_backend.services.graph.component_instance_v2_service.delete_component_instances_from_nodes")
    @patch("ada_backend.services.graph.component_instance_v2_service.delete_edge")
    @patch("ada_backend.services.graph.component_instance_v2_service.get_edges")
    @patch("ada_backend.services.graph.component_instance_v2_service.get_component_nodes")
    def test_cascades_edge_deletion(
        self, mock_get_nodes, mock_get_edges, mock_del_edge, mock_del_inst, mock_del_node, session, ids
    ):
        node = MagicMock()
        node.id = ids["instance_id"]
        mock_get_nodes.return_value = [node]

        edge = MagicMock()
        edge.id = uuid4()
        edge.source_node_id = ids["instance_id"]
        edge.target_node_id = uuid4()
        mock_get_edges.return_value = [edge]
        session.query.return_value.filter.return_value.all.return_value = []

        delete_component_from_graph(session, ids["graph_runner_id"], ids["instance_id"])

        mock_del_edge.assert_called_once_with(session, edge.id)


class TestSplitUnifiedParameters:
    def test_splits_by_kind(self):
        params = [
            PipelineParameterV2Schema(name="model", kind="parameter", value="gpt-4"),
            PipelineParameterV2Schema(
                name="messages",
                kind="input",
                field_expression={"expression_json": {"type": "literal", "value": "hi"}},
            ),
            PipelineParameterV2Schema(name="temperature", value=0.7),
        ]
        param_params, input_ports = _split_unified_parameters(params)
        assert len(param_params) == 2
        assert param_params[0].name == "model"
        assert param_params[1].name == "temperature"
        assert len(input_ports) == 1
        assert input_ports[0].name == "messages"
        assert input_ports[0].field_expression.expression_json["type"] == "literal"

    def test_empty_list(self):
        param_params, input_ports = _split_unified_parameters([])
        assert param_params == []
        assert input_ports == []

    def test_all_parameters(self):
        params = [
            PipelineParameterV2Schema(name="a", kind="parameter", value="1"),
            PipelineParameterV2Schema(name="b", value="2"),
        ]
        param_params, input_ports = _split_unified_parameters(params)
        assert len(param_params) == 2
        assert len(input_ports) == 0

    def test_all_inputs(self):
        params = [
            PipelineParameterV2Schema(
                name="x",
                kind="input",
                field_expression={"expression_json": {"type": "literal", "value": "a"}},
            ),
            PipelineParameterV2Schema(name="y", kind="input"),
        ]
        param_params, input_ports = _split_unified_parameters(params)
        assert len(param_params) == 0
        assert len(input_ports) == 2
        assert input_ports[0].field_expression.expression_json["type"] == "literal"
        assert input_ports[1].field_expression is None

    def test_preserves_optional_fields(self):
        port_def_id = uuid4()
        params = [
            PipelineParameterV2Schema(
                name="q", kind="input", description="search query", port_definition_id=port_def_id,
            ),
        ]
        _, input_ports = _split_unified_parameters(params)
        assert input_ports[0].description == "search query"
        assert input_ports[0].port_definition_id == port_def_id

    def test_defaults_to_parameter_kind(self):
        params = [PipelineParameterV2Schema(name="no_kind", value="val")]
        param_params, input_ports = _split_unified_parameters(params)
        assert len(param_params) == 1
        assert len(input_ports) == 0


class TestCreateComponentWithUnifiedParams:
    @patch("ada_backend.services.graph.component_instance_v2_service._sync_input_port_field_expressions")
    @patch("ada_backend.services.graph.component_instance_v2_service.upsert_component_node")
    @patch("ada_backend.services.graph.component_instance_v2_service.create_or_update_component_instance")
    def test_splits_unified_params_on_create(self, mock_create, mock_upsert_node, mock_sync, session, ids):
        created_id = uuid4()
        mock_create.return_value = created_id

        payload = ComponentCreateV2Schema(
            component_id=ids["component_id"],
            component_version_id=ids["component_version_id"],
            label="Agent",
            parameters=[
                {"name": "model", "kind": "parameter", "value": "gpt-4"},
                {
                    "name": "messages",
                    "kind": "input",
                    "field_expression": {"expression_json": {"type": "literal", "value": "hi"}},
                },
            ],
        )

        result = create_component_in_graph(session, ids["graph_runner_id"], ids["project_id"], payload)

        assert result == created_id
        instance_schema = mock_create.call_args[0][1]
        assert len(instance_schema.parameters) == 1
        assert instance_schema.parameters[0].name == "model"
        assert len(instance_schema.input_port_instances) == 1
        assert instance_schema.input_port_instances[0].name == "messages"
        mock_sync.assert_called_once()


class TestUpdatePreservesParametersWhenOmitted:
    @patch("ada_backend.services.graph.component_instance_v2_service._sync_input_port_field_expressions")
    @patch("ada_backend.services.graph.component_instance_v2_service.upsert_component_node")
    @patch("ada_backend.services.graph.component_instance_v2_service.create_or_update_component_instance")
    @patch("ada_backend.services.graph.component_instance_v2_service.get_component_nodes")
    @patch("ada_backend.services.graph.component_instance_v2_service.get_component_instance_by_id")
    def test_omitted_parameters_skips_replacement(
        self, mock_get_inst, mock_get_nodes, mock_create, mock_upsert_node, mock_sync, session, ids
    ):
        mock_instance = MagicMock()
        mock_instance.name = "Agent"
        mock_instance.component_version_id = ids["component_version_id"]
        mock_instance.component_version.component_id = ids["component_id"]
        mock_get_inst.return_value = mock_instance

        node = MagicMock()
        node.id = ids["instance_id"]
        node.is_start_node = False
        mock_get_nodes.return_value = [node]

        payload = ComponentUpdateV2Schema(label="Renamed Agent")

        update_single_component(session, ids["graph_runner_id"], ids["project_id"], ids["instance_id"], payload)

        instance_schema = mock_create.call_args[0][1]
        assert instance_schema.parameters is None
        assert instance_schema.name == "Renamed Agent"
        mock_sync.assert_not_called()


class TestUpdateComponentWithUnifiedParams:
    @patch("ada_backend.services.graph.component_instance_v2_service._sync_input_port_field_expressions")
    @patch("ada_backend.services.graph.component_instance_v2_service.upsert_component_node")
    @patch("ada_backend.services.graph.component_instance_v2_service.create_or_update_component_instance")
    @patch("ada_backend.services.graph.component_instance_v2_service.get_component_nodes")
    @patch("ada_backend.services.graph.component_instance_v2_service.get_component_instance_by_id")
    def test_splits_unified_params_on_update(
        self, mock_get_inst, mock_get_nodes, mock_create, mock_upsert_node, mock_sync, session, ids
    ):
        mock_instance = MagicMock()
        mock_instance.name = "Agent"
        mock_instance.component_version_id = ids["component_version_id"]
        mock_instance.component_version.component_id = ids["component_id"]
        mock_get_inst.return_value = mock_instance

        node = MagicMock()
        node.id = ids["instance_id"]
        node.is_start_node = False
        mock_get_nodes.return_value = [node]

        payload = ComponentUpdateV2Schema(
            parameters=[
                {"name": "model", "kind": "parameter", "value": "gpt-4"},
                {
                    "name": "query",
                    "kind": "input",
                    "field_expression": {"expression_json": {"type": "literal", "value": "test"}},
                },
            ],
        )

        update_single_component(session, ids["graph_runner_id"], ids["project_id"], ids["instance_id"], payload)

        instance_schema = mock_create.call_args[0][1]
        assert len(instance_schema.parameters) == 1
        assert len(instance_schema.input_port_instances) == 1
        mock_sync.assert_called_once()

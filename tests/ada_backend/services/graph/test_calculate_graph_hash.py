"""
Unit tests for _calculate_graph_hash function.

This function is critical for detecting graph modifications and must be thoroughly tested
to ensure it correctly identifies when graphs are identical or different.
"""

import uuid
import pytest
from uuid import UUID

from ada_backend.services.graph.update_graph_service import _calculate_graph_hash
from ada_backend.schemas.pipeline.graph_schema import GraphUpdateSchema, EdgeSchema
from ada_backend.schemas.pipeline.base import ComponentInstanceSchema, ComponentRelationshipSchema
from ada_backend.schemas.pipeline.port_mapping_schema import PortMappingSchema
from ada_backend.schemas.pipeline.field_expression_schema import FieldExpressionUpdateSchema
from ada_backend.schemas.parameter_schema import PipelineParameterSchema


def create_component_instance(
    instance_id: UUID = None,
    name: str = "Test Component",
    component_id: UUID = None,
    component_version_id: UUID = None,
    parameters: list = None,
    field_expressions: list = None,
    is_start_node: bool = False,
) -> ComponentInstanceSchema:
    """Helper to create a ComponentInstanceSchema with defaults."""
    if instance_id is None:
        instance_id = uuid.uuid4()
    if component_id is None:
        component_id = uuid.uuid4()
    if component_version_id is None:
        component_version_id = uuid.uuid4()
    if parameters is None:
        parameters = []
    if field_expressions is None:
        field_expressions = []

    return ComponentInstanceSchema(
        id=instance_id,
        name=name,
        ref="",
        is_start_node=is_start_node,
        component_id=component_id,
        component_version_id=component_version_id,
        parameters=parameters,
        field_expressions=field_expressions,
    )


def create_edge(edge_id: UUID = None, origin: UUID = None, destination: UUID = None, order: int = None) -> EdgeSchema:
    """Helper to create an EdgeSchema with defaults."""
    if edge_id is None:
        edge_id = uuid.uuid4()
    if origin is None:
        origin = uuid.uuid4()
    if destination is None:
        destination = uuid.uuid4()

    return EdgeSchema(id=edge_id, origin=origin, destination=destination, order=order)


def create_relationship(
    parent_id: UUID = None, child_id: UUID = None, parameter_name: str = "param", order: int = None
) -> ComponentRelationshipSchema:
    """Helper to create a ComponentRelationshipSchema with defaults."""
    if parent_id is None:
        parent_id = uuid.uuid4()
    if child_id is None:
        child_id = uuid.uuid4()

    return ComponentRelationshipSchema(
        parent_component_instance_id=parent_id,
        child_component_instance_id=child_id,
        parameter_name=parameter_name,
        order=order,
    )


def create_port_mapping(
    source_id: UUID = None,
    target_id: UUID = None,
    source_port: str = "output",
    target_port: str = "input",
    dispatch_strategy: str = "direct",
) -> PortMappingSchema:
    """Helper to create a PortMappingSchema with defaults."""
    if source_id is None:
        source_id = uuid.uuid4()
    if target_id is None:
        target_id = uuid.uuid4()

    return PortMappingSchema(
        source_instance_id=source_id,
        source_port_name=source_port,
        target_instance_id=target_id,
        target_port_name=target_port,
        dispatch_strategy=dispatch_strategy,
    )


class TestCalculateGraphHashIdentical:
    """Test that identical graphs produce the same hash."""

    def test_empty_graphs_produce_same_hash(self):
        """Empty graphs should produce the same hash."""
        graph1 = GraphUpdateSchema(component_instances=[], relationships=[], edges=[], port_mappings=[])
        graph2 = GraphUpdateSchema(component_instances=[], relationships=[], edges=[], port_mappings=[])

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 produces 64 hex characters

    def test_same_single_component_produces_same_hash(self):
        """Graphs with identical single components should produce the same hash."""
        instance_id = uuid.uuid4()
        component_id = uuid.uuid4()
        component_version_id = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id,
                    component_id=component_id,
                    component_version_id=component_version_id,
                )
            ],
            relationships=[],
            edges=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id,
                    component_id=component_id,
                    component_version_id=component_version_id,
                )
            ],
            relationships=[],
            edges=[],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 == hash2

    def test_same_graph_with_parameters_produces_same_hash(self):
        """Graphs with identical parameters should produce the same hash."""
        instance_id = uuid.uuid4()
        component_id = uuid.uuid4()
        component_version_id = uuid.uuid4()

        parameters = [
            PipelineParameterSchema(name="param1", value="value1", order=0),
            PipelineParameterSchema(name="param2", value=42, order=1),
        ]

        graph1 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id,
                    component_id=component_id,
                    component_version_id=component_version_id,
                    parameters=parameters,
                )
            ],
            relationships=[],
            edges=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id,
                    component_id=component_id,
                    component_version_id=component_version_id,
                    parameters=parameters,
                )
            ],
            relationships=[],
            edges=[],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 == hash2

    def test_same_graph_with_edges_produces_same_hash(self):
        """Graphs with identical edges should produce the same hash."""
        instance1_id = uuid.uuid4()
        instance2_id = uuid.uuid4()
        edge_id = uuid.uuid4()
        component_id = uuid.uuid4()
        component_version_id = uuid.uuid4()

        # Create the same objects to ensure identical serialization
        instance1 = create_component_instance(
            instance_id=instance1_id, component_id=component_id, component_version_id=component_version_id
        )
        instance2 = create_component_instance(
            instance_id=instance2_id, component_id=component_id, component_version_id=component_version_id
        )
        edge = create_edge(edge_id=edge_id, origin=instance1_id, destination=instance2_id)

        graph1 = GraphUpdateSchema(
            component_instances=[instance1, instance2],
            relationships=[],
            edges=[edge],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[instance1, instance2],
            relationships=[],
            edges=[edge],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 == hash2

    def test_same_graph_with_relationships_produces_same_hash(self):
        """Graphs with identical relationships should produce the same hash."""
        parent_id = uuid.uuid4()
        child_id = uuid.uuid4()
        component_id = uuid.uuid4()
        component_version_id = uuid.uuid4()

        # Create the same objects to ensure identical serialization
        parent = create_component_instance(
            instance_id=parent_id, component_id=component_id, component_version_id=component_version_id
        )
        child = create_component_instance(
            instance_id=child_id, component_id=component_id, component_version_id=component_version_id
        )
        relationship = create_relationship(parent_id=parent_id, child_id=child_id, parameter_name="input")

        graph1 = GraphUpdateSchema(
            component_instances=[parent, child],
            relationships=[relationship],
            edges=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[parent, child],
            relationships=[relationship],
            edges=[],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 == hash2

    def test_same_graph_with_port_mappings_produces_same_hash(self):
        """Graphs with identical port mappings should produce the same hash."""
        source_id = uuid.uuid4()
        target_id = uuid.uuid4()
        component_id = uuid.uuid4()
        component_version_id = uuid.uuid4()

        # Create the same objects to ensure identical serialization
        source = create_component_instance(
            instance_id=source_id, component_id=component_id, component_version_id=component_version_id
        )
        target = create_component_instance(
            instance_id=target_id, component_id=component_id, component_version_id=component_version_id
        )
        port_mapping = create_port_mapping(source_id=source_id, target_id=target_id)

        graph1 = GraphUpdateSchema(
            component_instances=[source, target],
            relationships=[],
            edges=[],
            port_mappings=[port_mapping],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[source, target],
            relationships=[],
            edges=[],
            port_mappings=[port_mapping],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 == hash2

    def test_same_graph_with_field_expressions_produces_same_hash(self):
        """Graphs with identical field expressions should produce the same hash."""
        instance_id = uuid.uuid4()
        component_id = uuid.uuid4()
        component_version_id = uuid.uuid4()

        # Create the same objects to ensure identical serialization
        field_expressions = [
            FieldExpressionUpdateSchema(field_name="field1", expression_text="ref.instance1.output"),
            FieldExpressionUpdateSchema(field_name="field2", expression_text="'literal'"),
        ]

        instance = create_component_instance(
            instance_id=instance_id,
            component_id=component_id,
            component_version_id=component_version_id,
            field_expressions=field_expressions,
        )

        graph1 = GraphUpdateSchema(
            component_instances=[instance],
            relationships=[],
            edges=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[instance],
            relationships=[],
            edges=[],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 == hash2

    def test_same_complex_graph_produces_same_hash(self):
        """Complex graphs with all fields should produce the same hash."""
        instance1_id = uuid.uuid4()
        instance2_id = uuid.uuid4()
        edge_id = uuid.uuid4()
        component_id = uuid.uuid4()
        component_version_id = uuid.uuid4()

        # Create the same objects to ensure identical serialization
        instance1 = create_component_instance(
            instance_id=instance1_id,
            name="Component 1",
            component_id=component_id,
            component_version_id=component_version_id,
            parameters=[PipelineParameterSchema(name="param", value="value")],
            field_expressions=[FieldExpressionUpdateSchema(field_name="field", expression_text="ref.x.output")],
            is_start_node=True,
        )
        instance2 = create_component_instance(
            instance_id=instance2_id,
            name="Component 2",
            component_id=component_id,
            component_version_id=component_version_id,
        )
        relationship = create_relationship(parent_id=instance1_id, child_id=instance2_id, parameter_name="input")
        edge = create_edge(edge_id=edge_id, origin=instance1_id, destination=instance2_id, order=0)
        port_mapping = create_port_mapping(source_id=instance1_id, target_id=instance2_id)

        graph1 = GraphUpdateSchema(
            component_instances=[instance1, instance2],
            relationships=[relationship],
            edges=[edge],
            port_mappings=[port_mapping],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[instance1, instance2],
            relationships=[relationship],
            edges=[edge],
            port_mappings=[port_mapping],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 == hash2


class TestCalculateGraphHashOrderSensitivity:
    """Test that hash is order-sensitive for lists (correct behavior for detecting changes)."""

    def test_component_instance_order_affects_hash(self):
        """Component instances in different orders should produce different hashes (order matters)."""
        instance1_id = uuid.uuid4()
        instance2_id = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(instance_id=instance1_id, name="First"),
                create_component_instance(instance_id=instance2_id, name="Second"),
            ],
            relationships=[],
            edges=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(instance_id=instance2_id, name="Second"),
                create_component_instance(instance_id=instance1_id, name="First"),
            ],
            relationships=[],
            edges=[],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2

    def test_edge_order_affects_hash(self):
        """Edges in different orders should produce different hashes (order matters)."""
        instance1_id = uuid.uuid4()
        instance2_id = uuid.uuid4()
        instance3_id = uuid.uuid4()
        edge1_id = uuid.uuid4()
        edge2_id = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(instance_id=instance1_id),
                create_component_instance(instance_id=instance2_id),
                create_component_instance(instance_id=instance3_id),
            ],
            relationships=[],
            edges=[
                create_edge(edge_id=edge1_id, origin=instance1_id, destination=instance2_id),
                create_edge(edge_id=edge2_id, origin=instance2_id, destination=instance3_id),
            ],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(instance_id=instance1_id),
                create_component_instance(instance_id=instance2_id),
                create_component_instance(instance_id=instance3_id),
            ],
            relationships=[],
            edges=[
                create_edge(edge_id=edge2_id, origin=instance2_id, destination=instance3_id),
                create_edge(edge_id=edge1_id, origin=instance1_id, destination=instance2_id),
            ],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2

    def test_relationship_order_affects_hash(self):
        """Relationships in different orders should produce different hashes (order matters)."""
        parent1_id = uuid.uuid4()
        parent2_id = uuid.uuid4()
        child_id = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(instance_id=parent1_id),
                create_component_instance(instance_id=parent2_id),
                create_component_instance(instance_id=child_id),
            ],
            relationships=[
                create_relationship(parent_id=parent1_id, child_id=child_id, parameter_name="input1"),
                create_relationship(parent_id=parent2_id, child_id=child_id, parameter_name="input2"),
            ],
            edges=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(instance_id=parent1_id),
                create_component_instance(instance_id=parent2_id),
                create_component_instance(instance_id=child_id),
            ],
            relationships=[
                create_relationship(parent_id=parent2_id, child_id=child_id, parameter_name="input2"),
                create_relationship(parent_id=parent1_id, child_id=child_id, parameter_name="input1"),
            ],
            edges=[],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2

    def test_port_mapping_order_affects_hash(self):
        """Port mappings in different orders should produce different hashes (order matters)."""
        source1_id = uuid.uuid4()
        source2_id = uuid.uuid4()
        target_id = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(instance_id=source1_id),
                create_component_instance(instance_id=source2_id),
                create_component_instance(instance_id=target_id),
            ],
            relationships=[],
            edges=[],
            port_mappings=[
                create_port_mapping(source_id=source1_id, target_id=target_id, source_port="output1"),
                create_port_mapping(source_id=source2_id, target_id=target_id, source_port="output2"),
            ],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(instance_id=source1_id),
                create_component_instance(instance_id=source2_id),
                create_component_instance(instance_id=target_id),
            ],
            relationships=[],
            edges=[],
            port_mappings=[
                create_port_mapping(source_id=source2_id, target_id=target_id, source_port="output2"),
                create_port_mapping(source_id=source1_id, target_id=target_id, source_port="output1"),
            ],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2

    def test_parameter_order_affects_hash(self):
        """Parameters in different orders should produce different hashes (order matters)."""
        instance_id = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id,
                    parameters=[
                        PipelineParameterSchema(name="param1", value="value1", order=0),
                        PipelineParameterSchema(name="param2", value="value2", order=1),
                    ],
                )
            ],
            relationships=[],
            edges=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id,
                    parameters=[
                        PipelineParameterSchema(name="param2", value="value2", order=1),
                        PipelineParameterSchema(name="param1", value="value1", order=0),
                    ],
                )
            ],
            relationships=[],
            edges=[],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2


class TestCalculateGraphHashDifferent:
    """Test that different graphs produce different hashes."""

    def test_different_component_ids_produce_different_hashes(self):
        """Graphs with different component IDs should produce different hashes."""
        instance_id = uuid.uuid4()
        component_id1 = uuid.uuid4()
        component_id2 = uuid.uuid4()
        component_version_id = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id, component_id=component_id1, component_version_id=component_version_id
                )
            ],
            relationships=[],
            edges=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id, component_id=component_id2, component_version_id=component_version_id
                )
            ],
            relationships=[],
            edges=[],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2

    def test_different_component_version_ids_produce_different_hashes(self):
        """Graphs with different component version IDs should produce different hashes."""
        instance_id = uuid.uuid4()
        component_id = uuid.uuid4()
        component_version_id1 = uuid.uuid4()
        component_version_id2 = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id, component_id=component_id, component_version_id=component_version_id1
                )
            ],
            relationships=[],
            edges=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id, component_id=component_id, component_version_id=component_version_id2
                )
            ],
            relationships=[],
            edges=[],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2

    def test_different_instance_ids_produce_different_hashes(self):
        """Graphs with different instance IDs should produce different hashes."""
        instance_id1 = uuid.uuid4()
        instance_id2 = uuid.uuid4()
        component_id = uuid.uuid4()
        component_version_id = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id1, component_id=component_id, component_version_id=component_version_id
                )
            ],
            relationships=[],
            edges=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id2, component_id=component_id, component_version_id=component_version_id
                )
            ],
            relationships=[],
            edges=[],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2

    def test_different_names_produce_different_hashes(self):
        """Graphs with different component names should produce different hashes."""
        instance_id = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[create_component_instance(instance_id=instance_id, name="Component A")],
            relationships=[],
            edges=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[create_component_instance(instance_id=instance_id, name="Component B")],
            relationships=[],
            edges=[],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2

    def test_different_parameter_values_produce_different_hashes(self):
        """Graphs with different parameter values should produce different hashes."""
        instance_id = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id,
                    parameters=[PipelineParameterSchema(name="param", value="value1")],
                )
            ],
            relationships=[],
            edges=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id,
                    parameters=[PipelineParameterSchema(name="param", value="value2")],
                )
            ],
            relationships=[],
            edges=[],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2

    def test_different_parameter_names_produce_different_hashes(self):
        """Graphs with different parameter names should produce different hashes."""
        instance_id = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id,
                    parameters=[PipelineParameterSchema(name="param1", value="value")],
                )
            ],
            relationships=[],
            edges=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id,
                    parameters=[PipelineParameterSchema(name="param2", value="value")],
                )
            ],
            relationships=[],
            edges=[],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2

    def test_different_parameter_types_produce_different_hashes(self):
        """Graphs with different parameter types should produce different hashes."""
        instance_id = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id,
                    parameters=[PipelineParameterSchema(name="param", value="42")],
                )
            ],
            relationships=[],
            edges=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id,
                    parameters=[PipelineParameterSchema(name="param", value=42)],
                )
            ],
            relationships=[],
            edges=[],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2

    def test_different_is_start_node_produces_different_hash(self):
        """Graphs with different is_start_node values should produce different hashes."""
        instance_id = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[create_component_instance(instance_id=instance_id, is_start_node=True)],
            relationships=[],
            edges=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[create_component_instance(instance_id=instance_id, is_start_node=False)],
            relationships=[],
            edges=[],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2

    def test_different_edges_produce_different_hashes(self):
        """Graphs with different edges should produce different hashes."""
        instance1_id = uuid.uuid4()
        instance2_id = uuid.uuid4()
        instance3_id = uuid.uuid4()
        edge_id = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(instance_id=instance1_id),
                create_component_instance(instance_id=instance2_id),
                create_component_instance(instance_id=instance3_id),
            ],
            relationships=[],
            edges=[create_edge(edge_id=edge_id, origin=instance1_id, destination=instance2_id)],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(instance_id=instance1_id),
                create_component_instance(instance_id=instance2_id),
                create_component_instance(instance_id=instance3_id),
            ],
            relationships=[],
            edges=[create_edge(edge_id=edge_id, origin=instance1_id, destination=instance3_id)],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2

    def test_different_edge_ids_produce_different_hashes(self):
        """Graphs with different edge IDs should produce different hashes."""
        instance1_id = uuid.uuid4()
        instance2_id = uuid.uuid4()
        edge_id1 = uuid.uuid4()
        edge_id2 = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(instance_id=instance1_id),
                create_component_instance(instance_id=instance2_id),
            ],
            relationships=[],
            edges=[create_edge(edge_id=edge_id1, origin=instance1_id, destination=instance2_id)],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(instance_id=instance1_id),
                create_component_instance(instance_id=instance2_id),
            ],
            relationships=[],
            edges=[create_edge(edge_id=edge_id2, origin=instance1_id, destination=instance2_id)],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2

    def test_different_edge_orders_produce_different_hashes(self):
        """Graphs with different edge orders should produce different hashes."""
        instance1_id = uuid.uuid4()
        instance2_id = uuid.uuid4()
        edge_id = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(instance_id=instance1_id),
                create_component_instance(instance_id=instance2_id),
            ],
            relationships=[],
            edges=[create_edge(edge_id=edge_id, origin=instance1_id, destination=instance2_id, order=0)],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(instance_id=instance1_id),
                create_component_instance(instance_id=instance2_id),
            ],
            relationships=[],
            edges=[create_edge(edge_id=edge_id, origin=instance1_id, destination=instance2_id, order=1)],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2

    def test_different_relationships_produce_different_hashes(self):
        """Graphs with different relationships should produce different hashes."""
        parent1_id = uuid.uuid4()
        parent2_id = uuid.uuid4()
        child_id = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(instance_id=parent1_id),
                create_component_instance(instance_id=parent2_id),
                create_component_instance(instance_id=child_id),
            ],
            relationships=[create_relationship(parent_id=parent1_id, child_id=child_id, parameter_name="input")],
            edges=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(instance_id=parent1_id),
                create_component_instance(instance_id=parent2_id),
                create_component_instance(instance_id=child_id),
            ],
            relationships=[create_relationship(parent_id=parent2_id, child_id=child_id, parameter_name="input")],
            edges=[],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2

    def test_different_relationship_parameter_names_produce_different_hashes(self):
        """Graphs with different relationship parameter names should produce different hashes."""
        parent_id = uuid.uuid4()
        child_id = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(instance_id=parent_id),
                create_component_instance(instance_id=child_id),
            ],
            relationships=[create_relationship(parent_id=parent_id, child_id=child_id, parameter_name="input1")],
            edges=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(instance_id=parent_id),
                create_component_instance(instance_id=child_id),
            ],
            relationships=[create_relationship(parent_id=parent_id, child_id=child_id, parameter_name="input2")],
            edges=[],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2

    def test_different_port_mappings_produce_different_hashes(self):
        """Graphs with different port mappings should produce different hashes."""
        source_id = uuid.uuid4()
        target_id = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(instance_id=source_id),
                create_component_instance(instance_id=target_id),
            ],
            relationships=[],
            edges=[],
            port_mappings=[create_port_mapping(source_id=source_id, target_id=target_id, source_port="output1")],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(instance_id=source_id),
                create_component_instance(instance_id=target_id),
            ],
            relationships=[],
            edges=[],
            port_mappings=[create_port_mapping(source_id=source_id, target_id=target_id, source_port="output2")],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2

    def test_different_port_mapping_dispatch_strategies_produce_different_hashes(self):
        """Graphs with different dispatch strategies should produce different hashes."""
        source_id = uuid.uuid4()
        target_id = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(instance_id=source_id),
                create_component_instance(instance_id=target_id),
            ],
            relationships=[],
            edges=[],
            port_mappings=[create_port_mapping(source_id=source_id, target_id=target_id, dispatch_strategy="direct")],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(instance_id=source_id),
                create_component_instance(instance_id=target_id),
            ],
            relationships=[],
            edges=[],
            port_mappings=[
                create_port_mapping(source_id=source_id, target_id=target_id, dispatch_strategy="broadcast")
            ],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2

    def test_different_field_expressions_produce_different_hashes(self):
        """Graphs with different field expressions should produce different hashes."""
        instance_id = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id,
                    field_expressions=[
                        FieldExpressionUpdateSchema(field_name="field", expression_text="ref.x.output")
                    ],
                )
            ],
            relationships=[],
            edges=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id,
                    field_expressions=[
                        FieldExpressionUpdateSchema(field_name="field", expression_text="ref.y.output")
                    ],
                )
            ],
            relationships=[],
            edges=[],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2

    def test_different_field_expression_names_produce_different_hashes(self):
        """Graphs with different field expression names should produce different hashes."""
        instance_id = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id,
                    field_expressions=[
                        FieldExpressionUpdateSchema(field_name="field1", expression_text="ref.x.output")
                    ],
                )
            ],
            relationships=[],
            edges=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id,
                    field_expressions=[
                        FieldExpressionUpdateSchema(field_name="field2", expression_text="ref.x.output")
                    ],
                )
            ],
            relationships=[],
            edges=[],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2

    def test_adding_component_produces_different_hash(self):
        """Adding a component should produce a different hash."""
        instance1_id = uuid.uuid4()
        instance2_id = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[create_component_instance(instance_id=instance1_id)],
            relationships=[],
            edges=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(instance_id=instance1_id),
                create_component_instance(instance_id=instance2_id),
            ],
            relationships=[],
            edges=[],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2

    def test_adding_edge_produces_different_hash(self):
        """Adding an edge should produce a different hash."""
        instance1_id = uuid.uuid4()
        instance2_id = uuid.uuid4()
        edge_id = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(instance_id=instance1_id),
                create_component_instance(instance_id=instance2_id),
            ],
            relationships=[],
            edges=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(instance_id=instance1_id),
                create_component_instance(instance_id=instance2_id),
            ],
            relationships=[],
            edges=[create_edge(edge_id=edge_id, origin=instance1_id, destination=instance2_id)],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2

    def test_adding_relationship_produces_different_hash(self):
        """Adding a relationship should produce a different hash."""
        parent_id = uuid.uuid4()
        child_id = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(instance_id=parent_id),
                create_component_instance(instance_id=child_id),
            ],
            relationships=[],
            edges=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(instance_id=parent_id),
                create_component_instance(instance_id=child_id),
            ],
            relationships=[create_relationship(parent_id=parent_id, child_id=child_id)],
            edges=[],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2

    def test_adding_port_mapping_produces_different_hash(self):
        """Adding a port mapping should produce a different hash."""
        source_id = uuid.uuid4()
        target_id = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(instance_id=source_id),
                create_component_instance(instance_id=target_id),
            ],
            relationships=[],
            edges=[],
            port_mappings=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(instance_id=source_id),
                create_component_instance(instance_id=target_id),
            ],
            relationships=[],
            edges=[],
            port_mappings=[create_port_mapping(source_id=source_id, target_id=target_id)],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2


class TestCalculateGraphHashEdgeCases:
    """Test edge cases and special values."""

    def test_none_parameter_values_produce_different_hashes_from_strings(self):
        """None parameter values should be distinguishable from string 'None'."""
        instance_id = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id,
                    parameters=[PipelineParameterSchema(name="param", value=None)],
                )
            ],
            relationships=[],
            edges=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id,
                    parameters=[PipelineParameterSchema(name="param", value="None")],
                )
            ],
            relationships=[],
            edges=[],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2

    def test_empty_strings_are_preserved(self):
        """Empty strings should be preserved and produce consistent hashes."""
        instance_id = uuid.uuid4()
        component_id = uuid.uuid4()
        component_version_id = uuid.uuid4()

        # Create the same objects to ensure identical serialization
        instance = create_component_instance(
            instance_id=instance_id,
            name="",
            component_id=component_id,
            component_version_id=component_version_id,
        )

        graph1 = GraphUpdateSchema(
            component_instances=[instance],
            relationships=[],
            edges=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[instance],
            relationships=[],
            edges=[],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 == hash2

    def test_empty_lists_produce_same_hash(self):
        """Empty lists in different fields should produce consistent hashes."""
        instance_id = uuid.uuid4()
        component_id = uuid.uuid4()
        component_version_id = uuid.uuid4()

        # Create the same objects to ensure identical serialization
        instance = create_component_instance(
            instance_id=instance_id,
            component_id=component_id,
            component_version_id=component_version_id,
            parameters=[],
            field_expressions=[],
        )

        graph1 = GraphUpdateSchema(
            component_instances=[instance],
            relationships=[],
            edges=[],
            port_mappings=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[instance],
            relationships=[],
            edges=[],
            port_mappings=[],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 == hash2

    def test_numeric_parameter_values_are_distinguished(self):
        """Different numeric types should produce different hashes."""
        instance_id = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id,
                    parameters=[PipelineParameterSchema(name="param", value=42)],
                )
            ],
            relationships=[],
            edges=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id,
                    parameters=[PipelineParameterSchema(name="param", value=42.0)],
                )
            ],
            relationships=[],
            edges=[],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2

    def test_boolean_parameter_values_are_distinguished(self):
        """Boolean values should be properly distinguished."""
        instance_id = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id,
                    parameters=[PipelineParameterSchema(name="param", value=True)],
                )
            ],
            relationships=[],
            edges=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id,
                    parameters=[PipelineParameterSchema(name="param", value=False)],
                )
            ],
            relationships=[],
            edges=[],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2

    def test_dict_parameter_values_are_handled(self):
        """Dictionary parameter values should be properly serialized."""
        instance_id = uuid.uuid4()
        component_id = uuid.uuid4()
        component_version_id = uuid.uuid4()

        # Create the same objects to ensure identical serialization
        param = PipelineParameterSchema(name="param", value={"key": "value"})
        instance = create_component_instance(
            instance_id=instance_id,
            component_id=component_id,
            component_version_id=component_version_id,
            parameters=[param],
        )

        graph1 = GraphUpdateSchema(
            component_instances=[instance],
            relationships=[],
            edges=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[instance],
            relationships=[],
            edges=[],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 == hash2

    def test_dict_parameter_values_with_different_content_produce_different_hashes(self):
        """Dictionary parameter values with different content should produce different hashes."""
        instance_id = uuid.uuid4()

        graph1 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id,
                    parameters=[PipelineParameterSchema(name="param", value={"key1": "value1"})],
                )
            ],
            relationships=[],
            edges=[],
        )

        graph2 = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id,
                    parameters=[PipelineParameterSchema(name="param", value={"key2": "value2"})],
                )
            ],
            relationships=[],
            edges=[],
        )

        hash1 = _calculate_graph_hash(graph1)
        hash2 = _calculate_graph_hash(graph2)

        assert hash1 != hash2

    def test_hash_is_deterministic(self):
        """Hash should be deterministic - same input always produces same output."""
        instance_id = uuid.uuid4()

        graph = GraphUpdateSchema(
            component_instances=[
                create_component_instance(
                    instance_id=instance_id,
                    name="Test",
                    parameters=[PipelineParameterSchema(name="param", value="value")],
                )
            ],
            relationships=[],
            edges=[],
        )

        hash1 = _calculate_graph_hash(graph)
        hash2 = _calculate_graph_hash(graph)
        hash3 = _calculate_graph_hash(graph)

        assert hash1 == hash2 == hash3

    def test_hash_format_is_hex_string(self):
        """Hash should be a 64-character hexadecimal string."""
        graph = GraphUpdateSchema(component_instances=[], relationships=[], edges=[])

        hash_value = _calculate_graph_hash(graph)

        assert isinstance(hash_value, str)
        assert len(hash_value) == 64
        assert all(c in "0123456789abcdef" for c in hash_value)

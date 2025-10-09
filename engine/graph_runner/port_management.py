"""
Graph Runner Port Management Functions

This module contains port management functions extracted from GraphRunner to keep the
main class focused on core execution logic. These functions handle port type discovery,
validation, and mapping synthesis.
"""

import logging
from typing import Any, Type, Optional

from engine.coercion_matrix import get_coercion_matrix
from engine.legacy_compatibility import get_unmigrated_output_type
from engine.graph_runner.types import PortMapping

LOGGER = logging.getLogger(__name__)


def get_component_port_type(component, port_name: str, is_input: bool) -> Type | None:
    """Get port type from any component (migrated or unmigrated).

    Uses two-tier discovery:
    1. Static: Get from Pydantic schema (any component with schema methods)
    2. Pattern-based: Get from known patterns (unmigrated components without schema methods)
    """
    if not component:
        return None

    # Tier 1: Static type discovery (any component with schema methods)
    try:
        schema = component.get_inputs_schema() if is_input else component.get_outputs_schema()
        field_info = schema.model_fields.get(port_name)
        if field_info:
            return field_info.annotation
    except Exception as e:
        LOGGER.debug(f"Could not extract static type for {port_name}: {e}")

    # Tier 2: Pattern-based (unmigrated outputs only)
    if not is_input:
        return get_unmigrated_output_type(component, port_name)

    return None  # Unknown input type for unmigrated components


def get_source_type(port_mapping: PortMapping, runnables: dict) -> str | Type:
    """Get the type of the source port."""
    source_runnable = runnables.get(port_mapping.source_instance_id)
    if not source_runnable:
        return str  # Default fallback for unknown components

    # Use unified type discovery
    source_type = get_component_port_type(source_runnable, port_mapping.source_port_name, is_input=False)
    return source_type if source_type is not None else str


def get_target_type(port_mapping: PortMapping, runnables: dict) -> str | Type:
    """Get the type of the target port."""
    target_runnable = runnables.get(port_mapping.target_instance_id)
    if not target_runnable:
        return str  # Default fallback for unknown components

    # Use unified type discovery
    target_type = get_component_port_type(target_runnable, port_mapping.target_port_name, is_input=True)
    return target_type if target_type is not None else str


def get_component_name(component_id: str, runnables: dict) -> str:
    """Get a human-readable component name for error messages."""
    runnable = runnables.get(component_id)
    if runnable:
        # Try to get the component name from various sources
        if hasattr(runnable, "component_attributes") and runnable.component_attributes:
            return runnable.component_attributes.component_instance_name
        elif hasattr(runnable, "__class__"):
            return runnable.__class__.__name__
        else:
            return f"Component({component_id[:8]}...)"
    else:
        return f"Unknown({component_id[:8]}...)"


def get_target_field_type(component, port_name: str) -> Optional[type]:
    """Extract target field type from component's input schema."""
    try:
        schema = component.get_inputs_schema()
        field_info = schema.model_fields.get(port_name)
        if field_info:
            return field_info.annotation
    except Exception as e:
        LOGGER.warning(f"Could not extract field type for {port_name}: {e}")
    # Fallback to str instead of None to avoid coercion errors
    return str


def get_source_type_for_mapping(port_mapping: PortMapping, source_value: Any, runnables: dict) -> Type:
    """Get the actual type of the source value for accurate coercion."""
    # Always use runtime type detection for accurate coercion
    # This ensures we coerce based on what the value actually IS, not what the schema says
    coercion_matrix = get_coercion_matrix()
    runtime_type = coercion_matrix._get_type_key(source_value)

    # For migrated components, verify schema matches runtime (debugging aid)
    source_runnable = runnables.get(port_mapping.source_instance_id)
    if source_runnable and hasattr(source_runnable, "migrated") and source_runnable.migrated:
        if hasattr(source_runnable, "get_outputs_schema"):
            try:
                schema = source_runnable.get_outputs_schema()
                field_info = schema.model_fields.get(port_mapping.source_port_name)
                if field_info and field_info.annotation != runtime_type:
                    LOGGER.warning(
                        f"Type mismatch for {port_mapping.source_instance_id}.{port_mapping.source_port_name}: "
                        f"schema declares {field_info.annotation}, runtime is {runtime_type}"
                    )
            except Exception as e:
                LOGGER.debug(f"Could not verify type from schema: {e}")

    return runtime_type


def apply_function_call_strategy(target_node_id: str, port_mappings: list[PortMapping]) -> dict[str, Any]:
    """Placeholder for transforming unstructured data into structured inputs."""
    LOGGER.warning("dispatch_strategy 'function_call' is not implemented yet.")
    return {}


def validate_port_mappings(port_mappings: list[PortMapping], runnables: dict):
    """Validate port mappings with appropriate strictness levels."""
    coercion_matrix = get_coercion_matrix()

    for port_mapping in port_mappings:
        # Get source and target types
        source_type = get_source_type(port_mapping, runnables)
        target_type = get_target_type(port_mapping, runnables)

        # Check if coercion is possible
        if not coercion_matrix.can_coerce(source_type, target_type):
            # Get component names for better error messages
            source_component_name = get_component_name(port_mapping.source_instance_id, runnables)
            target_component_name = get_component_name(port_mapping.target_instance_id, runnables)

            # Get components to check migration status
            source_comp = runnables.get(port_mapping.source_instance_id)
            target_comp = runnables.get(port_mapping.target_instance_id)

            # Check if both are migrated
            both_migrated = (
                hasattr(source_comp, "migrated")
                and source_comp.migrated
                and hasattr(target_comp, "migrated")
                and target_comp.migrated
            )

            if both_migrated:
                # STRICT: Fail fast for migrated components
                raise ValueError(
                    f"Cannot coerce {source_type} to {target_type} for mapping "
                    f"{source_component_name}.{port_mapping.source_port_name} -> "
                    f"{target_component_name}.{port_mapping.target_port_name}. "
                    f"Please check that the source component outputs the expected type."
                )
            else:
                # LENIENT: Warn for unmigrated components
                LOGGER.warning(
                    f"Coercion {source_type} to {target_type} may fail at runtime for mapping "
                    f"{source_component_name}.{port_mapping.source_port_name} -> "
                    f"{target_component_name}.{port_mapping.target_port_name}. "
                    f"Consider migrating components for better type safety."
                )
        else:
            # Check if types are unknown (both fallback to str)
            if source_type == str and target_type == str:
                # Unknown types - skip build-time validation
                LOGGER.info(
                    f"Skipping build-time validation for "
                    f"{port_mapping.source_instance_id}.{port_mapping.source_port_name} -> "
                    f"{port_mapping.target_instance_id}.{port_mapping.target_port_name} (types unknown)"
                )


def synthesize_default_mappings(
    graph, runnables: dict, input_node_id: str, existing_mappings: list[PortMapping]
) -> list[PortMapping]:
    """Create explicit direct port mappings for nodes with exactly one real predecessor
    when no mappings are provided. Uses canonical ports from runnables.

    - Skips start nodes that only depend on the virtual input node (passthrough).
    - Raises an error if a node has multiple real predecessors and no mappings.
    """
    new_mappings: list[PortMapping] = []

    # Build lookup index for existing mappings
    mappings_by_target: dict[str, list[PortMapping]] = {}
    for pm in existing_mappings:
        mappings_by_target.setdefault(pm.target_instance_id, []).append(pm)

    for node_id in graph.nodes():
        if node_id == input_node_id:
            continue
        existing = mappings_by_target.get(node_id, [])
        if existing:
            continue

        predecessors = list(graph.predecessors(node_id))
        is_start_node = input_node_id in predecessors
        real_predecessors = [p for p in predecessors if p != input_node_id]

        # Start-node passthrough remains implicit
        if is_start_node and not real_predecessors:
            continue

        if len(real_predecessors) == 0:
            # No inputs available; nothing to synthesize
            continue

        if len(real_predecessors) > 1:
            raise ValueError(
                "Node '{node}' has multiple incoming connections from {preds} without explicit port mappings. "
                "Please specify which outputs should connect to which inputs.".format(
                    node=node_id, preds=real_predecessors
                )
            )

        pred_id = real_predecessors[0]
        source_runnable = runnables.get(pred_id)
        target_runnable = runnables.get(node_id)

        # Determine canonical ports with sensible defaults
        source_port_name: str | None = None
        target_port_name: str | None = None
        # TODO: Remove hasattr check when all components are migrated
        if source_runnable and hasattr(source_runnable, "get_canonical_ports"):
            try:
                ports = source_runnable.get_canonical_ports()  # type: ignore[attr-defined]
                if isinstance(ports, dict):
                    # Resolve canonical port name to actual field name
                    canonical_output = ports.get("output")
                    if canonical_output:
                        source_port_name = canonical_output
            except Exception:
                source_port_name = None
        if target_runnable and hasattr(target_runnable, "get_canonical_ports"):
            try:
                ports = target_runnable.get_canonical_ports()  # type: ignore[attr-defined]
                if isinstance(ports, dict):
                    # Resolve canonical port name to actual field name
                    canonical_input = ports.get("input")
                    if canonical_input:
                        target_port_name = canonical_input
            except Exception:
                target_port_name = None

        source_port_name = source_port_name or "output"
        target_port_name = target_port_name or "input"

        new_mappings.append(
            PortMapping(
                source_instance_id=str(pred_id),
                source_port_name=source_port_name,
                target_instance_id=str(node_id),
                target_port_name=target_port_name,
                dispatch_strategy="direct",
            )
        )

    return new_mappings

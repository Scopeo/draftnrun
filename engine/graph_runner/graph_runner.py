import logging
from typing import Optional, Any
import json

import networkx as nx
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry import trace as trace_api

from engine.agent.types import AgentPayload, NodeData
from engine.coercion_matrix import create_default_coercion_matrix, CoercionMatrix
from engine.graph_runner.runnable import Runnable
from engine.graph_runner.types import Task, TaskState, PortMapping
from engine.graph_runner.port_management import (
    get_target_field_type,
    get_source_type_for_mapping,
    apply_function_call_strategy,
    validate_port_mappings,
    synthesize_default_mappings,
)
from engine.graph_runner.parameter_interpolation import ParameterInterpolator
from engine import legacy_compatibility
from engine.trace.trace_manager import TraceManager
from engine.trace.serializer import serialize_to_json
from engine.trace.span_context import get_tracing_span


LOGGER = logging.getLogger(__name__)


class GraphRunner:
    TRACE_SPAN_KIND: str = OpenInferenceSpanKindValues.CHAIN.value

    def __init__(
        self,
        graph: nx.DiGraph,
        runnables: dict[str, Runnable],
        start_nodes: list[str],
        trace_manager: TraceManager,
        *,
        port_mappings: list[dict[str, Any]] | None = None,
        node_parameters: dict[str, dict[str, Any]] | None = None,
        node_id_to_name: dict[str, str] | None = None,
        coercion_matrix: CoercionMatrix | None = None,
    ):
        self.trace_manager = trace_manager
        self.graph = graph
        self.runnables = runnables
        self.start_nodes = start_nodes
        self.run_context: dict[str, Any] = {}
        # Initialize coercion matrix - use provided one or create default
        self.coercion_matrix = coercion_matrix or create_default_coercion_matrix()

        # Convert raw mapping dicts into structured PortMapping objects.
        self.port_mappings: list[PortMapping] = [
            PortMapping(
                source_instance_id=str(pm["source_instance_id"]),
                source_port_name=pm["source_port_name"],
                target_instance_id=str(pm["target_instance_id"]),
                target_port_name=pm["target_port_name"],
                dispatch_strategy=pm.get("dispatch_strategy", "direct"),
            )
            for pm in port_mappings or []
        ]

        # Build a quick lookup index for mappings by their target node ID.
        self._mappings_by_target: dict[str, list[PortMapping]] = {}
        for pm in self.port_mappings:
            self._mappings_by_target.setdefault(pm.target_instance_id, []).append(pm)

        # Store unified parameters for each node
        # Format: {node_id: {param_name: value}}
        # Value can be:
        # - Static: "hello world", 42, true
        # - Reference: "{{@node1.output}}"
        # - Hybrid: "Result: {{@node1.output}}, Status: {{@node2.status}}"
        self.node_parameters: dict[str, dict[str, Any]] = node_parameters or {}

        # Store component name to ID mapping for {{@name.field}} syntax resolution
        # Format: {node_id: component_name}
        # Example: {"uuid-123": "my_input_component"}
        self.node_id_to_name: dict[str, str] = node_id_to_name or {}

        self.tasks: dict[str, Task] = {}
        self._input_node_id = "__input__"
        self._add_virtual_input_node()
        # Synthesize explicit default mappings for single-predecessor nodes without mappings
        self._synthesize_default_mappings()
        self._validate_graph()
        validate_port_mappings(self.port_mappings, self.runnables)

    def _initialize_execution(self, input_data: dict[str, Any]) -> None:
        """Initialize the execution state including dependencies and input data."""
        LOGGER.debug("Initializing dependency counts")
        self.tasks.clear()
        for node_id in self.graph.nodes():
            pending_deps: int = self.graph.in_degree(node_id)
            self.tasks[node_id] = Task(pending_deps=pending_deps)

        LOGGER.debug("Initializing input node")
        self.tasks[self._input_node_id] = Task(
            pending_deps=0,
            result=NodeData(data=input_data, ctx=self.run_context),
            state=TaskState.COMPLETED,
        )

        # Process the virtual input node's successors
        for successor in self.graph.successors(self._input_node_id):
            self.tasks[successor].decrement_pending_deps()

    def _next_task(self) -> Optional[str]:
        """
        Get the next (ready) task to run. Stops iteration as soon as a ready task is found.
        If no ready tasks are found, returns None.
        """
        ready_tasks_gen = (node_id for node_id, task in self.tasks.items() if task.state == TaskState.READY)
        return next(ready_tasks_gen, None)

    async def run(self, *inputs: AgentPayload | dict, **kwargs) -> AgentPayload | dict:
        """Run the graph."""
        input_data = inputs[0]

        if any(isinstance(input_data, dict) for input_data in inputs):
            LOGGER.warning("There are dictionaries in the inputs, this will be deprecated in the future")

        # Isolate trace if this is a root execution
        is_root_execution = kwargs.pop("is_root_execution", False)

        with self.trace_manager.start_span("Workflow", isolate_context=is_root_execution) as span:
            trace_input = serialize_to_json(input_data, shorten_string=True)
            span.set_attributes(
                {
                    SpanAttributes.OPENINFERENCE_SPAN_KIND: self.TRACE_SPAN_KIND,
                    SpanAttributes.INPUT_VALUE: trace_input,
                }
            )
            # Legacy compatibility shim: accept AgentPayload or dict and normalize to dict for internal runner.
            # Long-term target: GraphRunner.run should accept NodeData only; remove when callers stop
            # passing AgentPayload/dict and provide NodeData instead.
            if isinstance(input_data, AgentPayload):
                normalized_input: dict[str, Any] = input_data.model_dump(exclude_unset=True, exclude_none=True)
            else:
                normalized_input = input_data  # type: ignore[assignment]
            final_output = await self._run_without_io_trace(normalized_input)

            trace_output = serialize_to_json(final_output, shorten_string=True)
            span.set_attributes(
                {
                    SpanAttributes.OUTPUT_VALUE: trace_output,
                }
            )
            span.set_status(trace_api.StatusCode.OK)

            params = get_tracing_span()
            if params:
                span_json = json.loads(span.to_json())
                params.trace_id = span_json["context"]["trace_id"]

            return final_output

    async def _run_without_io_trace(self, input_data: dict[str, Any]) -> AgentPayload:
        """The core execution loop of the graph."""
        self._initialize_execution(input_data)

        while node_id := self._next_task():
            task = self.tasks[node_id]
            assert task.state == TaskState.READY, f"Node '{node_id}' is not ready"
            runnable = self.runnables[node_id]
            node_inputs_data = self._gather_inputs(node_id)
            input_packet = NodeData(data=node_inputs_data, ctx=self.run_context)
            result_any = await runnable.run(input_packet)
            result_packet = legacy_compatibility.normalize_output_to_node_data(result_any, self.run_context)
            task.complete(result_packet)
            self.run_context.update(result_packet.ctx or {})
            LOGGER.debug(f"Node '{node_id}' completed execution with result: {result_packet}")

            for successor in self.graph.successors(node_id):
                self.tasks[successor].decrement_pending_deps()

        return legacy_compatibility.collect_legacy_outputs(self.graph, self.tasks, self._input_node_id, self.runnables)

    def _add_virtual_input_node(self):
        """Add a virtual input node and connect it to all start nodes."""
        self.graph.add_node(self._input_node_id)
        for start_node in self.start_nodes:
            self.graph.add_edge(
                self._input_node_id,
                start_node,
            )

    def _get_resolved_outputs(self) -> dict[str, dict[str, Any]]:
        """
        Get all outputs from completed tasks for template resolution.

        Returns:
            Dict mapping node_id -> {port_name: value} for all completed nodes
            Also indexes by component name if available for {{@name.field}} syntax
        """
        resolved_outputs: dict[str, dict[str, Any]] = {}
        for node_id, task in self.tasks.items():
            if task.state == TaskState.COMPLETED and task.result and task.result.data:
                # Index by node ID (UUID)
                resolved_outputs[node_id] = task.result.data

                # ALSO index by component name if available (for {{@name.field}} syntax)
                if node_id in self.node_id_to_name:
                    component_name = self.node_id_to_name[node_id]
                    resolved_outputs[component_name] = task.result.data
        return resolved_outputs

    def _process_unified_parameters(self, node_id: str, input_data: dict[str, Any]) -> None:
        """Process unified parameters and add to input_data."""
        unified_params = self.node_parameters.get(node_id, {})
        if not unified_params:
            return

        LOGGER.debug(f"Processing {len(unified_params)} unified parameters for node '{node_id}'")
        resolved_outputs = self._get_resolved_outputs()

        for param_name, param_value in unified_params.items():
            # Check if value contains references (template syntax)
            if isinstance(param_value, str) and ParameterInterpolator.is_template(param_value):
                # Resolve references (supports static, reference, and hybrid)
                try:
                    resolved_value = ParameterInterpolator.resolve_template(param_value, resolved_outputs)
                    input_data[param_name] = resolved_value
                    LOGGER.debug(
                        f"Unified param '{param_name}' for node '{node_id}': "
                        f"template='{param_value}' -> value='{resolved_value}'"
                    )
                except ValueError as e:
                    LOGGER.error(f"Failed to resolve unified parameter '{param_name}' for node '{node_id}': {e}")
                    raise ValueError(
                        f"Failed to resolve parameter '{param_name}' for component '{node_id}': {e}"
                    ) from e
            else:
                # Static value - use directly
                input_data[param_name] = param_value
                LOGGER.debug(f"Unified param '{param_name}' for node '{node_id}': static value='{param_value}'")


    def _gather_inputs(self, node_id: str) -> dict[str, Any]:
        """Assembles the input data for a node using the unified parameter system.

        Priority order:
        1. Unified node_parameters - HIGHEST PRIORITY
        2. Port mappings - Lowest priority

        In the unified system, each parameter value can be:
        - Static: Used directly (e.g., "hello", 42, true)
        - Reference: Resolved at runtime (e.g., "{{@node1.output}}")
        - Hybrid: Mix of static and references (e.g., "Result: {{@node1.output}}")
        """
        input_data: dict[str, Any] = {}

        # Process unified parameters first (if present)
        self._process_unified_parameters(node_id, input_data)

        # Process port mappings AFTER unified parameters
        # Unified parameters take precedence over port mappings
        port_mappings_for_target = self._mappings_by_target.get(node_id, [])
        predecessors = list(self.graph.predecessors(node_id))
        is_start_node = self._input_node_id in predecessors

        # Check if node has any parameters defined (unified)
        unified_params = self.node_parameters.get(node_id, {})

        if not port_mappings_for_target:
            # If node is start and has no other deps, pass through initial input or apply canonical transformation
            real_predecessors = [p for p in predecessors if p != self._input_node_id]
            if is_start_node and not real_predecessors:
                input_task_result = self.tasks[self._input_node_id].result
                passthrough_data = input_task_result.data if input_task_result else {}

                # Apply canonical transformation for components with canonical input ports
                # This handles the common case where global input has "message" but component expects "messages"
                runnable = self.runnables.get(node_id)
                if runnable and hasattr(runnable, "get_canonical_ports"):
                    canonical_ports = runnable.get_canonical_ports()
                    canonical_input = canonical_ports.get("input")

                    # If component has a canonical input port and it's not already set
                    if canonical_input and canonical_input not in input_data:
                        # Try to populate from common alternative field names in global input
                        if canonical_input == "messages":
                            from engine.agent.types import ChatMessage

                            # Try "message" (singular) first
                            if "message" in passthrough_data:
                                message_content = passthrough_data["message"]
                                if isinstance(message_content, str):
                                    input_data["messages"] = [ChatMessage(role="user", content=message_content)]
                                    LOGGER.debug(
                                        f"Canonical transformation for node '{node_id}': "
                                        f"transformed 'message' (str) -> 'messages' (list[ChatMessage])"
                                    )
                            # Try "messages" (plural) in passthrough
                            elif "messages" in passthrough_data:
                                messages_content = passthrough_data["messages"]
                                # If it's already a list of ChatMessage, use it
                                if isinstance(messages_content, list):
                                    input_data["messages"] = messages_content
                                    LOGGER.debug(
                                        f"Canonical transformation for node '{node_id}': "
                                        f"passed through 'messages' from global input"
                                    )

                # FIX: Check if there are any template-based (runtime) unified parameters
                # Static configuration parameters (like allow_tool_shortcuts)
                # shouldn't prevent runtime data passthrough
                has_template_unified_params = any(
                    isinstance(v, str) and ParameterInterpolator.is_template(v) for v in unified_params.values()
                )

                # If no template-based unified params, pass through everything (old behavior)
                if not has_template_unified_params:
                    # Merge passthrough data, but don't override already-set fields (preserves static config params)
                    for key, value in passthrough_data.items():
                        if key not in input_data:
                            input_data[key] = value

        direct_port_mappings = [
            port_mapping for port_mapping in port_mappings_for_target if port_mapping.dispatch_strategy == "direct"
        ]
        for port_mapping in direct_port_mappings:
            # Skip if already set by unified parameters
            if port_mapping.target_port_name in input_data:
                LOGGER.debug(
                    f"Skipping port mapping for '{port_mapping.target_port_name}' - "
                    f"already set by higher priority parameter"
                )
                continue

            if (
                port_mapping.source_instance_id in self.tasks
                and self.tasks[port_mapping.source_instance_id].state == TaskState.COMPLETED
            ):
                task_result = self.tasks[port_mapping.source_instance_id].result
                if task_result and port_mapping.source_port_name in task_result.data:
                    source_value = task_result.data[port_mapping.source_port_name]

                    # Check if target component is unmigrated
                    target_component = self.runnables.get(node_id)
                    is_unmigrated = target_component and not hasattr(target_component, "migrated")

                    if is_unmigrated:
                        input_data = task_result.data
                    else:
                        target_type = (
                            get_target_field_type(target_component, port_mapping.target_port_name)
                            if target_component
                            else str
                        )
                        source_type = get_source_type_for_mapping(port_mapping, source_value, self.runnables)
                        LOGGER.debug(
                            f"Legacy port mapping: {port_mapping.source_instance_id}.{port_mapping.source_port_name} "
                            f"({source_type}) → {port_mapping.target_instance_id}.{port_mapping.target_port_name} "
                            f"({target_type})"
                        )
                        coerced_value = self.coercion_matrix.coerce(source_value, target_type, source_type)
                        input_data[port_mapping.target_port_name] = coerced_value
                else:
                    LOGGER.warning(
                        f"Source port '{port_mapping.source_port_name}' not found in output of "
                        f"node '{port_mapping.source_instance_id}'"
                    )

        function_call_port_mappings = [
            port_mapping
            for port_mapping in port_mappings_for_target
            if port_mapping.dispatch_strategy == "function_call"
        ]
        if function_call_port_mappings:
            structured_values = apply_function_call_strategy(node_id, function_call_port_mappings)
            # Only update keys not already set by unified parameters
            for key, value in structured_values.items():
                if key not in input_data:
                    input_data[key] = value

        return input_data

    def reset(self):
        """Reset the graph runner state to allow reuse.

        This clears all task state and results, allowing the same GraphRunner
        instance to be used for multiple executions.
        """
        self.tasks.clear()

    def _validate_graph(self):
        """Ensures the graph and mappings are consistent before execution."""
        if len(set(self.runnables.keys())) != len(self.runnables):
            raise ValueError("All runnables ids must be unique")

        if set(self.runnables.keys()) != set(self.graph.nodes()) - {self._input_node_id}:
            raise ValueError("All runnables must be in the graph")


    def _synthesize_default_mappings(self) -> None:
        """Create explicit direct port mappings for nodes with exactly one real predecessor
        when no mappings are provided. Uses canonical ports from runnables.

        - Skips start nodes that only depend on the virtual input node (passthrough).
        - Raises an error if a node has multiple real predecessors and no mappings.
        """
        new_mappings = synthesize_default_mappings(self.graph, self.runnables, self._input_node_id, self.port_mappings)

        if not new_mappings:
            return

        # Extend mappings and rebuild the index for consistency
        self.port_mappings.extend(new_mappings)
        self._mappings_by_target = {}
        for pm in self.port_mappings:
            self._mappings_by_target.setdefault(pm.target_instance_id, []).append(pm)

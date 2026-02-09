import json
import logging
from typing import Any, Iterator, Optional, TypedDict

import networkx as nx
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry import trace as trace_api

from engine import legacy_compatibility
from engine.coercion_matrix import CoercionMatrix, create_default_coercion_matrix
from engine.components.types import AgentPayload, NodeData
from engine.field_expressions.ast import ExpressionNode, LiteralNode, RefNode
from engine.field_expressions.traversal import select_nodes
from engine.graph_runner.field_expression_management import evaluate_expression
from engine.graph_runner.port_management import (
    apply_function_call_strategy,
    get_source_type_for_mapping,
    get_target_field_type,
    synthesize_default_mappings,
    validate_port_mappings,
)
from engine.graph_runner.runnable import Runnable
from engine.graph_runner.types import PortMapping, Task, TaskState
from engine.trace.serializer import serialize_to_json
from engine.trace.span_context import get_tracing_span
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)


class GraphRunner:
    TRACE_SPAN_KIND: str = OpenInferenceSpanKindValues.CHAIN.value

    class ExpressionSpec(TypedDict):
        target_instance_id: str
        field_name: str
        expression_ast: ExpressionNode

    def __init__(
        self,
        graph: nx.DiGraph,
        runnables: dict[str, Runnable],
        start_nodes: list[str],
        trace_manager: TraceManager,
        *,
        port_mappings: list[dict[str, Any]] | None = None,
        expressions: list[ExpressionSpec] | None = None,
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

        # Build lookup index for expressions by (target, field)
        self.expressions: list[GraphRunner.ExpressionSpec] = expressions or []
        self._expressions_by_target_ast: dict[tuple[str, str], ExpressionNode] = {
            (expr["target_instance_id"], expr["field_name"]): expr["expression_ast"] for expr in self.expressions
        }

        self.tasks: dict[str, Task] = {}
        self._input_node_id = "__input__"
        self._add_virtual_input_node()
        # Synthesize explicit default mappings for single-predecessor nodes without mappings
        self._synthesize_default_mappings()
        # Augment graph topology with dependencies from port mappings (including synthesized) and expressions
        self._augment_graph_with_dependencies()
        self._validate_graph()
        validate_port_mappings(self.port_mappings, self.runnables)
        self._validate_expressions()

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
            span.set_attributes({
                SpanAttributes.OPENINFERENCE_SPAN_KIND: self.TRACE_SPAN_KIND,
                SpanAttributes.INPUT_VALUE: trace_input,
            })
            # Legacy compatibility shim: accept AgentPayload or dict and normalize to dict for internal runner.
            # Long-term target: GraphRunner.run should accept NodeData only; remove when callers stop
            # passing AgentPayload/dict and provide NodeData instead.
            if isinstance(input_data, AgentPayload):
                normalized_input: dict[str, Any] = input_data.model_dump(exclude_unset=True, exclude_none=True)
            else:
                normalized_input = input_data  # type: ignore[assignment]
            final_output = await self._run_without_io_trace(normalized_input)

            trace_output = serialize_to_json(final_output, shorten_string=True)
            span.set_attributes({
                SpanAttributes.OUTPUT_VALUE: trace_output,
            })
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

            should_halt = result_packet.data.get("should_halt", False)
            if should_halt:
                LOGGER.info(f"Node '{node_id}' signaled to halt downstream execution")
                self._halt_downstream_execution(node_id)
            else:
                port_halt_signals = {}
                for port_name, port_value in result_packet.data.items():
                    if isinstance(port_value, dict) and "should_halt" in port_value:
                        port_halt_signals[port_name] = port_value["should_halt"]

                if port_halt_signals:
                    LOGGER.debug(f"Node '{node_id}' has per-port halt signals: {port_halt_signals}")
                    self._selective_halt_downstream(node_id, port_halt_signals)
                else:
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

    def _augment_graph_with_dependencies(self) -> None:
        """Augment the graph with edges derived from port mappings and expressions, then validate DAG.

        - For each port mapping, ensure an edge source -> target exists.
        - For each expression with ref nodes, add edges ref.instance -> target.
        - Forbid self-loops; raise on cycles.
        """
        for pm in self.port_mappings:
            src = pm.source_instance_id
            dst = pm.target_instance_id
            if not self.graph.has_edge(src, dst):
                self.graph.add_edge(src, dst)

        for (target, _field), expr_ast in self._expressions_by_target_ast.items():
            ref_nodes: Iterator[RefNode] = select_nodes(expr_ast, lambda n: isinstance(n, RefNode))
            src_instances = {ref_node.instance for ref_node in ref_nodes}
            for src in src_instances:
                if not self.graph.has_edge(src, target):
                    self.graph.add_edge(src, target)

        if not nx.is_directed_acyclic_graph(self.graph):
            raise ValueError(
                f"Graph contains cycles after dependency augmentation. Edges: {dict(self.graph.edges())}",
            )

    def _gather_inputs(self, node_id: str) -> dict[str, Any]:
        """Assembles the input data for a node based on explicit mappings,
        keeping start-node passthrough. Default mapping synthesis happens during
        initialization so mappings should be explicit here.
        """
        input_data: dict[str, Any] = {}
        port_mappings_for_target = self._mappings_by_target.get(node_id, [])
        predecessors = list(self.graph.predecessors(node_id))
        is_start_node = self._input_node_id in predecessors

        if not port_mappings_for_target:
            # If node is start and has no other deps, pass through initial input
            real_predecessors = [p for p in predecessors if p != self._input_node_id]
            if is_start_node and not real_predecessors:
                input_task_result = self.tasks[self._input_node_id].result
                input_data = input_task_result.data if input_task_result else {}
            else:
                input_data = {}

        direct_port_mappings = [
            port_mapping for port_mapping in port_mappings_for_target if port_mapping.dispatch_strategy == "direct"
        ]
        for port_mapping in direct_port_mappings:
            if (
                port_mapping.source_instance_id in self.tasks
                and self.tasks[port_mapping.source_instance_id].state == TaskState.COMPLETED
            ):
                task_result = self.tasks[port_mapping.source_instance_id].result
                if task_result and port_mapping.source_port_name in task_result.data:
                    source_value = task_result.data[port_mapping.source_port_name]

                    if isinstance(source_value, dict) and "data" in source_value and "should_halt" in source_value:
                        source_value = source_value["data"]

                    # Check if target component is unmigrated (doesn't have migrated attribute)
                    target_component = self.runnables.get(node_id)
                    is_unmigrated = bool(target_component) and not hasattr(target_component, "migrated")

                    if is_unmigrated:
                        # For unmigrated components, pass the entire output structure
                        # instead of trying to extract individual fields
                        input_data = task_result.data
                    else:
                        # For migrated components, use coercion system
                        value_to_coerce = source_value
                        # TODO: Pure refs with keys create coupling between port mappings and expressions.
                        # Decouple after system is stable/harmonized
                        pure_ref_expr = self._expressions_by_target_ast.get((node_id, port_mapping.target_port_name))

                        if isinstance(pure_ref_expr, RefNode) and pure_ref_expr.key:
                            if not isinstance(source_value, dict):
                                raise ValueError(
                                    f"Key extraction '::{pure_ref_expr.key}' cannot be used on "
                                    f"{port_mapping.source_instance_id}.{port_mapping.source_port_name}: "
                                    f"port value is not a dict, got {type(source_value)}"
                                )
                            if pure_ref_expr.key not in source_value:
                                raise ValueError(
                                    f"Key '{pure_ref_expr.key}' not found in dict from "
                                    f"{port_mapping.source_instance_id}.{port_mapping.source_port_name}"
                                )
                            value_to_coerce = source_value[pure_ref_expr.key]
                            LOGGER.debug(
                                f"Extracted key '{pure_ref_expr.key}' from {port_mapping.source_instance_id}."
                                f"{port_mapping.source_port_name}"
                            )

                        target_type = (
                            get_target_field_type(target_component, port_mapping.target_port_name)
                            if target_component
                            else str
                        )

                        source_type = get_source_type_for_mapping(port_mapping, value_to_coerce, self.runnables)
                        LOGGER.debug(
                            f"Coercing {port_mapping.source_instance_id}.{port_mapping.source_port_name} "
                            f"({source_type}) → {port_mapping.target_instance_id}.{port_mapping.target_port_name} "
                            f"({target_type})"
                        )
                        coerced_value = self.coercion_matrix.coerce(value_to_coerce, target_type, source_type)
                        input_data[port_mapping.target_port_name] = coerced_value
                else:
                    LOGGER.warning(
                        f"Source port '{port_mapping.source_port_name}' not found in output of "
                        f"node '{port_mapping.source_instance_id}' for mapping to "
                        f"'{node_id}.{port_mapping.target_port_name}'."
                    )

        function_call_port_mappings = [
            port_mapping
            for port_mapping in port_mappings_for_target
            if port_mapping.dispatch_strategy == "function_call"
        ]
        if function_call_port_mappings:
            structured_values = apply_function_call_strategy(node_id, function_call_port_mappings)
            input_data.update(structured_values)

        # Handle field expressions for inputs (non-ref expressions like concat/literal)
        # Apply regardless of whether explicit port mappings exist; non-ref expressions override mapped values.
        # Pure-ref expressions are ignored at runtime (port mappings authoritative).
        if self._expressions_by_target_ast:
            non_ref_expressions: list[tuple[str, ExpressionNode]] = [
                (field_name, expr_ast)
                for (target_id, field_name), expr_ast in self._expressions_by_target_ast.items()
                if target_id == node_id and not isinstance(expr_ast, RefNode)
            ]

            target_component = self.runnables[node_id]
            for field_name, expression_ast in non_ref_expressions:
                if (
                    field_name in input_data
                    and input_data[field_name] is not None
                    and input_data[field_name] != ""
                    and isinstance(expression_ast, LiteralNode)
                    and (expression_ast.value == "" or expression_ast.value is None)
                ):
                    LOGGER.debug(
                        f"Skipping empty LiteralNode expression for {node_id}.{field_name} "
                        f"because port mapping already provided value"
                    )
                    continue

                def _to_string(value: Any) -> str:
                    return self.coercion_matrix.coerce(value, str, type(value))

                evaluated_value = evaluate_expression(
                    expression_ast,
                    field_name,
                    self.tasks,
                    to_string=_to_string,
                )
                LOGGER.debug(f"Evaluating non-ref expression for {node_id}.{field_name}")
                target_type = get_target_field_type(target_component, field_name)
                # Only coerce if the value is a string and target type is different
                # JsonBuildNode returns dict/list directly, no coercion needed
                if (
                    isinstance(evaluated_value, str)
                    and target_type is not str
                    and self.coercion_matrix.should_attempt_coercion(target_type)
                ):
                    LOGGER.warning(f"Coercing expression result to {target_type} for field {field_name}")
                    evaluated_value = self.coercion_matrix.coerce(evaluated_value, target_type, str)
                input_data[field_name] = evaluated_value
                LOGGER.debug(f"Set {node_id}.{field_name} from expression: {evaluated_value}")

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

    def _validate_expressions(self):
        """
        Ensures all expressions target valid components and fields.
        - Expressions must target valid components
        - Expressions must target fields that are in the component's input schema
        """
        for expression in self.expressions:
            target_instance_id = expression["target_instance_id"]
            field_name = expression["field_name"]

            if target_instance_id not in self.runnables:
                raise ValueError(
                    f"Expression targets non-existent component '{target_instance_id}' "
                    f"for field '{field_name}'. Component must exist in the graph."
                )

            target_component = self.runnables[target_instance_id]
            if not bool(getattr(target_component, "migrated", False)):
                raise ValueError(
                    f"Expressions are not supported for unmigrated component '{target_instance_id}'. "
                    f"Please migrate the component or remove the expression for field '{field_name}'."
                )

            inputs_schema = target_component.get_inputs_schema()
            input_fields = list(inputs_schema.model_fields.keys())
            if field_name not in input_fields:
                raise ValueError(
                    f"Formula targets non-existent field '{field_name}' on component '{target_instance_id}'. "
                    f"Available input fields: {input_fields}"
                )

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

    # TODO: Add a ControlFlowManager to handle the control flow of the graph
    def _halt_downstream_execution(self, source_node_id: str) -> None:
        """Mark all downstream nodes from source as completed without execution."""
        visited = set()
        queue = [source_node_id]

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            for successor in self.graph.successors(current):
                if successor not in visited:
                    task = self.tasks[successor]
                    if task.state != TaskState.COMPLETED:
                        LOGGER.debug(f"Halting execution for downstream node '{successor}'")
                        # Mark as completed with empty result to prevent execution
                        task.state = TaskState.COMPLETED
                        task.result = NodeData(data={}, ctx=self.run_context)
                    queue.append(successor)

    def _should_halt_successor(
        self,
        successor: str,
        source_node_id: str,
        port_halt_signals: dict[str, bool],
    ) -> bool:
        """
        Determine if a successor should be halted based on port mappings and halt signals.

        Args:
            successor: The successor node to check
            source_node_id: The source node with halt signals
            port_halt_signals: Dict mapping port names to their should_halt boolean values

        Returns:
            True if successor should be halted, False if it should continue
        """
        # Find port mappings from source to this successor
        mappings = [
            pm for pm in self._mappings_by_target.get(successor, []) if pm.source_instance_id == source_node_id
        ]

        # If there are no mappings from this router, halt by default
        # (the successor shouldn't execute without explicit route connection)
        if not mappings:
            return True

        # Check mappings to determine if successor should halt
        has_route_port_mapping = False
        has_output_port_mapping = False

        for mapping in mappings:
            source_port = mapping.source_port_name

            # Check if this is a specific route port (route_0, route_1, etc.)
            if source_port in port_halt_signals:
                has_route_port_mapping = True
                # Check if this route port is halted
                if port_halt_signals[source_port]:
                    return True
            # Check if connected to default output port (matched route data)
            elif source_port == "output":
                has_output_port_mapping = True

        # If connected to 'output' port and no specific route port, check if any route matched
        if not has_route_port_mapping and has_output_port_mapping:
            # If ALL routes are halted, halt this successor too
            if all(port_halt_signals.values()):
                return True
            else:
                return False
        # If no route port mappings and no output port, halt by default
        elif not has_route_port_mapping and not has_output_port_mapping:
            return True

        return False

    def _selective_halt_downstream(self, source_node_id: str, port_halt_signals: dict[str, bool]) -> None:
        """
        Selectively halt or continue downstream nodes based on which output ports they connect to.

        Args:
            source_node_id: The node that produced the output with per-port halt signals
            port_halt_signals: Dict mapping port names to their should_halt boolean values
        """
        LOGGER.debug(f"Selective halt for {source_node_id} with signals: {port_halt_signals}")

        for successor in self.graph.successors(source_node_id):
            should_halt = self._should_halt_successor(successor, source_node_id, port_halt_signals)

            if should_halt:
                LOGGER.debug(f"Halting successor '{successor}'")
                self._halt_downstream_execution(successor)
            else:
                LOGGER.debug(f"Continuing successor '{successor}'")
                self.tasks[successor].decrement_pending_deps()

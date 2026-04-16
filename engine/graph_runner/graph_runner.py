import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Iterator, Optional, TypedDict

import networkx as nx
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry import trace as trace_api

from engine import legacy_compatibility
from engine.coercion_matrix import CoercionError, CoercionMatrix, create_default_coercion_matrix
from engine.components.types import AgentPayload, ExecutionDirective, ExecutionStrategy, NodeData
from engine.field_expressions.ast import ExpressionNode, RefNode
from engine.field_expressions.errors import FieldExpressionError
from engine.field_expressions.traversal import select_nodes
from engine.graph_runner.field_expression_management import evaluate_expression
from engine.graph_runner.port_management import get_target_field_type
from engine.graph_runner.runnable import Runnable
from engine.graph_runner.types import Task, TaskState
from engine.trace.serializer import serialize_to_json
from engine.trace.span_context import get_tracing_span, set_tracing_span
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
        expressions: list[ExpressionSpec] | None = None,
        coercion_matrix: CoercionMatrix | None = None,
        variables: dict[str, Any] | None = None,
        event_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ):
        self.trace_manager = trace_manager
        self.event_callback = event_callback
        self.graph = graph
        self.runnables = runnables
        self.start_nodes = start_nodes
        self.run_context: dict[str, Any] = {}
        self.variables: dict[str, Any] = variables or {}
        self.coercion_matrix = coercion_matrix or create_default_coercion_matrix()

        self.expressions: list[GraphRunner.ExpressionSpec] = expressions or []
        self._expressions_by_target_ast: dict[tuple[str, str], ExpressionNode] = {
            (expr["target_instance_id"], expr["field_name"]): expr["expression_ast"] for expr in self.expressions
        }
        self._expressions_by_node: dict[str, list[tuple[str, ExpressionNode]]] = {}
        for (target_id, field_name), expr_ast in self._expressions_by_target_ast.items():
            self._expressions_by_node.setdefault(target_id, []).append((field_name, expr_ast))

        self.tasks: dict[str, Task] = {}
        self._input_node_id = "__input__"
        self._add_virtual_input_node()
        self._augment_graph_with_dependencies()
        self._validate_graph()
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
            params = get_tracing_span()
            if params:
                span_json = json.loads(span.to_json())
                trace_id = span_json["context"]["trace_id"]
                params.trace_id = trace_id
                set_tracing_span(trace_id=trace_id)

            # TODO(security): `input_data` is the raw run payload (ctx + user inputs).
            # serialize_to_json masks SecretStr only — plaintext secrets coming from clients
            # need catalog-level "sensitive port" metadata to be redacted here.
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
            if self.event_callback:
                try:
                    await self.event_callback({"type": "node.started", "node_id": node_id})
                except Exception:
                    LOGGER.debug(f"event_callback error on node.started for '{node_id}'", exc_info=True)
                # Inject the callback into the component so it can emit intermediate events.
                if hasattr(runnable, "event_callback"):
                    runnable.event_callback = self.event_callback
            result_any = await runnable.run(input_packet)
            result_packet = legacy_compatibility.normalize_output_to_node_data(result_any, self.run_context)
            task.complete(result_packet)
            self.run_context.update(result_packet.ctx or {})
            LOGGER.debug(f"Node '{node_id}' completed execution with result: {result_packet}")
            if self.event_callback:
                try:
                    await self.event_callback({"type": "node.completed", "node_id": node_id})
                except Exception:
                    LOGGER.debug(f"event_callback error on node.completed for '{node_id}'", exc_info=True)

            # Extract execution directive (normalized to CONTINUE if None)
            # NOTE: If we add many more execution strategies in the future,
            # consider using Strategy Pattern with dedicated handler classes.
            directive = result_packet.directive

            # TODO: Remove after IfElse migration - Backward compatibility
            # IfElse currently uses should_halt in data dict (legacy pattern)
            if directive is None and result_packet.data.get("should_halt", False):
                directive = ExecutionDirective(strategy=ExecutionStrategy.HALT)

            directive = directive or ExecutionDirective()

            if directive.strategy == ExecutionStrategy.CONTINUE:
                # Default: execute all successors
                for successor in self.graph.successors(node_id):
                    self.tasks[successor].decrement_pending_deps()

            elif directive.strategy == ExecutionStrategy.HALT:
                LOGGER.info(f"Node '{node_id}' signaled to halt downstream execution")
                self._halt_downstream_execution(node_id)

            elif directive.strategy == ExecutionStrategy.SELECTIVE_EDGE_INDICES:
                LOGGER.debug(f"Node '{node_id}' selective execution on indices: {directive.selected_edge_indices}")
                self._execute_selective_edges_indices(node_id, directive.selected_edge_indices)

        return legacy_compatibility.collect_legacy_outputs(self.graph, self.tasks, self._input_node_id, self.runnables)

    def _add_virtual_input_node(self):
        """Add a virtual input node and connect it to all start nodes."""
        self.graph.add_node(self._input_node_id)
        for start_node in self.start_nodes:
            self.graph.add_edge(
                self._input_node_id,
                start_node,
            )

    def _add_dependency_edge_if_needed(self, src: str, dst: str) -> None:
        """Add a dependency edge src → dst unless execution ordering is already guaranteed.

        Skips the edge when a transitive path already exists — adding it would be redundant
        and would cause selective-routing nodes (Routers) to treat the extra edge as an
        unmatched route and halt the destination unnecessarily.

        Always adds the edge when:
        - src == dst  (self-loop must be preserved so the DAG check can raise)
        - either node is not yet in the graph  (unknown nodes must reach _validate_graph)
        """
        if self.graph.has_edge(src, dst):
            return
        already_reachable = (
            src != dst
            and src in self.graph
            and dst in self.graph
            and nx.has_path(self.graph, src, dst)
        )
        if not already_reachable:
            self.graph.add_edge(src, dst)

    def _augment_graph_with_dependencies(self) -> None:
        """Augment the graph with edges derived from expressions, then validate DAG.

        For each expression with ref nodes, add edges ref.instance -> target.
        """
        for (target, _field), expr_ast in self._expressions_by_target_ast.items():
            ref_nodes: Iterator[RefNode] = select_nodes(expr_ast, lambda n: isinstance(n, RefNode))
            for src in {ref_node.instance for ref_node in ref_nodes}:
                self._add_dependency_edge_if_needed(src, target)

        if not nx.is_directed_acyclic_graph(self.graph):
            raise ValueError(
                f"Graph contains cycles after dependency augmentation. Edges: {dict(self.graph.edges())}",
            )

    def _eval_expression_and_set_input(
        self,
        node_id: str,
        field_name: str,
        expression_ast: ExpressionNode,
        target_component: Any,
        input_data: dict[str, Any],
        *,
        log_prefix: str = "expression",
    ) -> None:
        """Evaluate a field expression, coerce to target type if needed, set input_data[field_name].
        Raises FieldExpressionError on evaluation failure.
        """

        def _to_string(value: Any) -> str:
            return self.coercion_matrix.coerce(value, str, type(value))

        evaluated_value = evaluate_expression(
            expression_ast,
            field_name,
            self.tasks,
            to_string=_to_string,
            variables=self.variables,
        )
        target_type = get_target_field_type(target_component, field_name)
        if target_type and self.coercion_matrix.should_attempt_coercion(target_type):
            source_type = type(evaluated_value)
            try:
                coerced = self.coercion_matrix.coerce(evaluated_value, target_type, source_type)
            except CoercionError as e:
                raise FieldExpressionError(
                    f"Failed to coerce {source_type.__name__} to {target_type} for field {field_name}: {e}"
                ) from e
            if coerced is not evaluated_value:
                LOGGER.warning(
                    "Coercing expression result from %s to %s for field %s",
                    source_type.__name__,
                    target_type,
                    field_name,
                )
                evaluated_value = coerced
        input_data[field_name] = evaluated_value
        # Don't log `evaluated_value`: after ConcatNode unwrap it can be a plaintext
        # rendering of a SecretStr (e.g. "Bearer sk-...").
        LOGGER.debug(
            "Set %s.%s from %s (type=%s)",
            node_id,
            field_name,
            log_prefix,
            type(evaluated_value).__name__,
        )

    def _gather_inputs(self, node_id: str) -> dict[str, Any]:
        """Assemble input data for a node by evaluating all field expressions.

        Graph entrypoint nodes (no real predecessors) receive the initial input data as base.
        All field expressions are then evaluated and set uniformly.
        """
        input_data: dict[str, Any] = {}
        predecessors = list(self.graph.predecessors(node_id))
        is_graph_entrypoint = self._input_node_id in predecessors
        real_predecessors = [p for p in predecessors if p != self._input_node_id]

        if is_graph_entrypoint and not real_predecessors:
            input_task_result = self.tasks[self._input_node_id].result
            input_data = dict(input_task_result.data) if input_task_result else {}

        target_component = self.runnables.get(node_id)
        for field_name, expr_ast in self._expressions_by_node.get(node_id, []):
            self._eval_expression_and_set_input(node_id, field_name, expr_ast, target_component, input_data)

        return input_data

    def reset(self):
        """Reset the graph runner state to allow reuse.

        This clears all task state and results, allowing the same GraphRunner
        instance to be used for multiple executions.
        """
        self.tasks.clear()

    async def close(self) -> None:
        for runnable in self.runnables.values():
            try:
                await runnable.close()
            except Exception as e:
                LOGGER.error(f"Error closing runnable: {e}", exc_info=True)

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

    def _halt_downstream_execution(self, source_node_id: str) -> None:
        """Mark source node and all its downstream nodes as halted without execution.
        Nodes already COMPLETED are left unchanged."""
        root_task = self.tasks[source_node_id]
        if root_task.state not in (TaskState.COMPLETED, TaskState.HALTED):
            LOGGER.debug(f"Halting execution for root node '{source_node_id}'")
            root_task.state = TaskState.HALTED
            root_task.result = NodeData(data={}, ctx=self.run_context)
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
                    if task.state not in (TaskState.COMPLETED, TaskState.HALTED):
                        LOGGER.debug(f"Halting execution for downstream node '{successor}'")
                        task.state = TaskState.HALTED
                        task.result = NodeData(data={}, ctx=self.run_context)
                    queue.append(successor)

    def _execute_selective_edges_indices(self, source_node_id: str, selected_edge_indices: list[int]) -> None:
        """
        Selectively execute downstream nodes based on selected edge indices.
        Only successors connected via edges with order in selected_edge_indices will execute.

        Args:
            source_node_id: The source node ID
            selected_edge_indices: List of edge order values that should execute (e.g., [0, 2])
        """
        LOGGER.info(f"Selective execution for {source_node_id} with selected edge indices: {selected_edge_indices}")
        # TODO: Temporary workaround for executing selective edges.
        # We should refactor this to implement a more robust execution strategy.
        # Possibly move the selection logic to the frontend and rely on edge IDs instead of execution order.
        for successor in self.graph.successors(source_node_id):
            edge_data = self.graph.get_edge_data(source_node_id, successor)
            edge_order = edge_data.get("order") if edge_data else None

            if edge_order is not None and edge_order in selected_edge_indices:
                LOGGER.info(f"Executing '{successor}' via edge order={edge_order}")
                self.tasks[successor].decrement_pending_deps()
            else:
                # No match - halt this successor
                LOGGER.info(f"Halting '{successor}' (order {edge_order} not in selected indices)")
                self._halt_downstream_execution(successor)

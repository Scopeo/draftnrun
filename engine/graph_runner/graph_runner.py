import logging
from enum import StrEnum
from dataclasses import dataclass
from typing import Optional, Any
import json

import networkx as nx
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry import trace as trace_api

from engine.agent.types import AgentPayload, ChatMessage, NodeData
from engine.graph_runner.runnable import Runnable
from engine.trace.trace_manager import TraceManager
from engine.trace.serializer import serialize_to_json
from engine.trace.span_context import get_tracing_span


LOGGER = logging.getLogger(__name__)


class TaskState(StrEnum):
    NOT_READY = "not_ready"
    READY = "ready"
    COMPLETED = "completed"


@dataclass
class Task:
    """Tracks task data and state."""

    pending_deps: int
    state: TaskState = TaskState.NOT_READY
    result: Optional[NodeData] = None

    def decrement_pending_deps(self):
        """Decrement pending dependencies, marking the task as ready
        if dependencies are now satisfied."""
        if self.state != TaskState.NOT_READY:
            raise ValueError("Cannot decrement pending dependencies for a non-ready task")

        if self.pending_deps <= 0:
            raise ValueError("Pending dependencies cannot be negative")
        self.pending_deps -= 1

        if self.pending_deps == 0:
            self.state = TaskState.READY

    def complete(self, result: NodeData):
        """Mark the task as completed with a result."""
        if self.state != TaskState.READY:
            raise ValueError("Cannot complete a non-ready task")
        self.state = TaskState.COMPLETED
        self.result = result


@dataclass
class PortMapping:
    """A structured representation of a connection between two nodes' ports."""

    source_instance_id: str
    source_port_name: str
    target_instance_id: str
    target_port_name: str
    dispatch_strategy: str = "direct"


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
    ):
        self.trace_manager = trace_manager
        self.graph = graph
        self.runnables = runnables
        self.start_nodes = start_nodes
        self.run_context: dict[str, Any] = {}

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

        self.tasks: dict[str, Task] = {}
        self._input_node_id = "__input__"
        self._add_virtual_input_node()
        # Synthesize explicit default mappings for single-predecessor nodes without mappings
        self._synthesize_default_mappings()
        self._validate_graph()

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
            result_packet = _normalize_output_to_node_data(result_any, self.run_context)
            task.complete(result_packet)
            self.run_context.update(result_packet.ctx or {})
            LOGGER.debug(f"Node '{node_id}' completed execution with result: {result_packet}")

            for successor in self.graph.successors(node_id):
                self.tasks[successor].decrement_pending_deps()

        return self._collect_outputs()

    def _add_virtual_input_node(self):
        """Add a virtual input node and connect it to all start nodes."""
        self.graph.add_node(self._input_node_id)
        for start_node in self.start_nodes:
            self.graph.add_edge(
                self._input_node_id,
                start_node,
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
                return input_task_result.data if input_task_result else {}
            # Otherwise, no explicit mappings -> no inputs
            return {}

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
                    input_data[port_mapping.target_port_name] = task_result.data[port_mapping.source_port_name]
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
            structured_values = self._apply_function_call_strategy(node_id, function_call_port_mappings)
            input_data.update(structured_values)

        return input_data

    def _apply_function_call_strategy(self, target_node_id: str, port_mappings: list[PortMapping]) -> dict[str, Any]:
        """Placeholder for transforming unstructured data into structured inputs."""
        LOGGER.warning("dispatch_strategy 'function_call' is not implemented yet.")
        return {}

    def _collect_outputs(self) -> AgentPayload:
        """Legacy compatibility shim: collect outputs and convert to AgentPayload.

        New multi-port graphs should eventually return structured data instead of
        forcing a single assistant message. This will be revisited post-migration.
        """
        leaf_nodes: list[str] = []
        for node_id in self.graph.nodes():
            if self.graph.out_degree(node_id) == 0 and node_id != self._input_node_id:
                leaf_nodes.append(node_id)

        leaf_pairs: list[tuple[str, NodeData]] = []
        for node_id in leaf_nodes:
            task = self.tasks.get(node_id)
            if task and task.state == TaskState.COMPLETED and task.result is not None:
                leaf_pairs.append((node_id, task.result))

        if not leaf_pairs:
            return AgentPayload(messages=[ChatMessage(role="assistant", content="")])

        # Legacy compatibility shim: reduce a NodeData to a single string for message content
        def pick_canonical_output(node_id: str, node_data: NodeData) -> str:
            runnable = self.runnables.get(node_id)
            preferred_key: str | None = None
            if runnable and hasattr(runnable, "get_canonical_ports"):
                try:
                    ports = runnable.get_canonical_ports()
                    preferred_key = ports.get("output") if isinstance(ports, dict) else None
                except Exception:
                    preferred_key = None
            data = node_data.data or {}
            value = None
            if preferred_key and preferred_key in data:
                value = data.get(preferred_key)
            if value is None:
                value = data.get("output", data.get("response"))

            # Handle dicts that look like ChatMessages (from model_dump)
            if isinstance(value, dict) and "content" in value and isinstance(value.get("content"), str):
                return value["content"]  # type: ignore

            # Handle actual ChatMessage objects
            if isinstance(value, ChatMessage):
                return value.content or ""

            # Handle plain strings
            if isinstance(value, str):
                return value

            # Fallback: serialize the value of the port, or the whole data dict if no value found
            if value is not None:
                return serialize_to_json(value, shorten_string=True)

            return serialize_to_json(data, shorten_string=True)

        if len(leaf_pairs) == 1:
            node_id, nd = leaf_pairs[0]
            content = pick_canonical_output(node_id, nd)
            data = nd.data or {}
            return AgentPayload(
                messages=[ChatMessage(role="assistant", content=content)],
                is_final=bool(data.get("is_final", False)),
                artifacts=data.get("artifacts", {}) or {},
            )

        # Multiple leaves: concatenate
        message_content = ""
        for i, (node_id, nd) in enumerate(leaf_pairs, start=1):
            content = pick_canonical_output(node_id, nd)
            message_content += f"Result from output {i}:\n{content}\n\n"
        return AgentPayload(messages=[ChatMessage(role="assistant", content=message_content.strip())])

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
        new_mappings: list[PortMapping] = []
        for node_id in self.graph.nodes():
            if node_id == self._input_node_id:
                continue
            existing = self._mappings_by_target.get(node_id, [])
            if existing:
                continue

            predecessors = list(self.graph.predecessors(node_id))
            is_start_node = self._input_node_id in predecessors
            real_predecessors = [p for p in predecessors if p != self._input_node_id]

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
            source_runnable = self.runnables.get(pred_id)
            target_runnable = self.runnables.get(node_id)

            # Determine canonical ports with sensible defaults
            source_port_name: str | None = None
            target_port_name: str | None = None
            # TODO: Remove hasattr check when all components are migrated
            if source_runnable and hasattr(source_runnable, "get_canonical_ports"):
                try:
                    ports = source_runnable.get_canonical_ports()  # type: ignore[attr-defined]
                    if isinstance(ports, dict):
                        source_port_name = ports.get("output")
                except Exception:
                    source_port_name = None
            if target_runnable and hasattr(target_runnable, "get_canonical_ports"):
                try:
                    ports = target_runnable.get_canonical_ports()  # type: ignore[attr-defined]
                    if isinstance(ports, dict):
                        target_port_name = ports.get("input")
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

        if not new_mappings:
            return

        # Extend mappings and rebuild the index for consistency
        self.port_mappings.extend(new_mappings)
        self._mappings_by_target = {}
        for pm in self.port_mappings:
            self._mappings_by_target.setdefault(pm.target_instance_id, []).append(pm)


# --- Backward Compatibility Shims ---


def _normalize_output_to_node_data(result: Any, run_context: dict[str, Any]) -> NodeData:
    """Backward-compatibility: normalize runnable outputs to NodeData.

    Supports NodeData, AgentPayload, and dict outputs from legacy components.
    """
    if isinstance(result, NodeData):
        return result
    if isinstance(result, AgentPayload):
        return NodeData(data=result.model_dump(exclude_unset=True, exclude_none=True), ctx=run_context)
    if isinstance(result, dict):
        return NodeData(data=result, ctx=run_context)
    raise TypeError(f"Unsupported runnable output type: {type(result)}")

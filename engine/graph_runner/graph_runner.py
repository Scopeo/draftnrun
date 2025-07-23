import logging
from enum import StrEnum
from dataclasses import dataclass
from typing import Optional

import networkx as nx
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry import trace as trace_api

from engine.agent.agent import AgentPayload, ChatMessage
from engine.graph_runner.runnable import Runnable
from engine.trace.trace_manager import TraceManager
from engine.trace.serializer import serialize_to_json

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
    result: Optional[AgentPayload] = None

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

    def complete(self, result: AgentPayload):
        """Mark the task as completed with a result."""
        if self.state != TaskState.READY:
            raise ValueError("Cannot complete a non-ready task")
        self.state = TaskState.COMPLETED
        self.result = result


# TODO: Delete after AgentInput/Output is refactored
def _merge_agent_outputs(agent_outputs: list[AgentPayload]) -> AgentPayload:
    """Merge a list of AgentOutputs into a single AgentOutput."""
    if len(agent_outputs) == 1:
        return agent_outputs[0]

    message = ""
    for i, output in enumerate(agent_outputs, start=1):
        message += f"Result from agent {i}:\n{output.last_message.content}\n\n"
    return AgentPayload(messages=[ChatMessage(role="assistant", content=message)])


class GraphRunner:
    TRACE_SPAN_KIND: str = OpenInferenceSpanKindValues.CHAIN.value

    def __init__(
        self,
        graph: nx.DiGraph,
        runnables: dict[str, Runnable],
        start_nodes: list[str],
        trace_manager: TraceManager,
    ):
        self.trace_manager = trace_manager
        self.graph = graph
        self.runnables = runnables
        self.start_nodes = start_nodes

        # Track node dependencies and results
        self.tasks: dict[str, Task] = {}

        self._input_node_id = "__input__"
        self._add_virtual_input_node()

        self._validate_graph()

    def _initialize_execution(self, input_data: dict) -> None:
        """Initialize the execution state including dependencies and input data."""
        LOGGER.debug("Initializing dependency counts")
        for node_id in self.graph.nodes():
            pending_deps = self.graph.in_degree(node_id)
            self.tasks[node_id] = Task(pending_deps=pending_deps)

        LOGGER.debug("Initializing input node")
        self.tasks[self._input_node_id] = Task(
            pending_deps=0,
            result=input_data,
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

        # Isolate trace if this is a root execution
        is_root_execution = kwargs.pop("is_root_execution", False)

        with self.trace_manager.start_span("Workflow", isolate_context=is_root_execution) as span:
            trace_input = serialize_to_json(input_data)
            span.set_attributes(
                {
                    SpanAttributes.OPENINFERENCE_SPAN_KIND: self.TRACE_SPAN_KIND,
                    SpanAttributes.INPUT_VALUE: trace_input,
                }
            )
            final_output = await self._run_without_trace(input_data, **kwargs)
            # TODO: Update trace when AgentInput/Output is refactored
            trace_output = serialize_to_json(final_output)
            span.set_attributes(
                {
                    SpanAttributes.OUTPUT_VALUE: trace_output,
                }
            )
            span.set_status(trace_api.StatusCode.OK)

            return final_output

    async def _run_without_trace(self, *inputs: AgentPayload | dict, **kwargs) -> AgentPayload | dict:
        input_data = inputs[0]
        self._initialize_execution(input_data)
        while node_id := self._next_task():
            task = self.tasks[node_id]
            assert task.state == TaskState.READY, f"Node '{node_id}' is not ready"

            input_list = self._gather_inputs(node_id)

            runnable = self.runnables[node_id]
            result = await runnable.run(*tuple(input_list))

            LOGGER.debug(f"Node '{node_id}' completed execution with result: {result}")
            task.complete(result)

            for successor in self.graph.successors(node_id):
                # if it reaches 0, it will be marked as ready
                self.tasks[successor].decrement_pending_deps()

        # Collect outputs from leaf nodes
        final_output = self._collect_outputs()
        return final_output

    def _add_virtual_input_node(self):
        """Add a virtual input node and connect it to all start nodes."""
        self.graph.add_node(self._input_node_id)
        for start_node in self.start_nodes:
            self.graph.add_edge(
                self._input_node_id,
                start_node,
            )

    # NOTE: Our current AgentInput/Output loses the message history
    # TODO: Fix this after AgentInput/Output is refactored
    def _gather_inputs(self, node_id: str) -> list[AgentPayload]:
        """Gather inputs for a node from its predecessors"""

        results: list[AgentPayload] = []

        ordered_predecessors = sorted(
            self.graph.predecessors(node_id), key=lambda pred: self.graph[pred][node_id].get("order", 0)
        )
        for predecessor in ordered_predecessors:
            task = self.tasks[predecessor]
            assert task.result is not None, (
                f"Node {node_id} depends on {predecessor} but its results",
                "are not available. This indicates a bug in dependency tracking.",
            )
            results.append(task.result)

        return results

    def _collect_outputs(self) -> AgentPayload:
        """Collect outputs from leaf nodes in the graph.

        Returns:
            Combined output data from all leaf nodes
        """
        leaf_outputs: list[AgentPayload] = []
        for node_id in self.graph.nodes():
            task = self.tasks[node_id]
            is_leaf = self.graph.out_degree(node_id) == 0
            task_completed = task.state == TaskState.COMPLETED
            if is_leaf and task_completed:
                assert task.result is not None, (
                    f"Node {node_id} is a leaf node but its result is not available. "
                    "This indicates a bug in dependency tracking.",
                )
                leaf_outputs.append(task.result)

        return _merge_agent_outputs(leaf_outputs)

    def _validate_graph(self):
        if len(set(self.runnables.keys())) != len(self.runnables):
            raise ValueError("All runnables ids must be unique")

        if set(self.runnables.keys()) != set(self.graph.nodes()) - {self._input_node_id}:
            raise ValueError("All runnables must be in the graph")

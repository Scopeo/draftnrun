from engine.components.component import Component
from engine.components.types import AgentPayload, ComponentAttributes, ToolDescription
from engine.graph_runner.graph_runner import GraphRunner
from engine.trace.trace_manager import TraceManager

DEFAULT_GRAPH_RUNNER_BLOCK_TOOL_DESCRIPTION = ToolDescription(
    name="Graph Runner",
    description="Execute a graph workflow",
    tool_properties={},
    required_tool_properties=[],
)


class GraphRunnerBlock(Component):
    def __init__(
        self,
        trace_manager: TraceManager,
        graph_runner: GraphRunner,
        component_attributes: ComponentAttributes,
        tool_description: ToolDescription = DEFAULT_GRAPH_RUNNER_BLOCK_TOOL_DESCRIPTION,
    ):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self._graph_runner = graph_runner

    async def _run_without_io_trace(self, *inputs: AgentPayload, **kwargs) -> AgentPayload:
        input_data: AgentPayload = inputs[0]

        result = await self._graph_runner.run(input_data)

        # TODO: This should be enforced on the GraphRunner level
        if not isinstance(result, AgentPayload):
            raise ValueError("GraphRunnerBlock must return an AgentPayload")

        return result

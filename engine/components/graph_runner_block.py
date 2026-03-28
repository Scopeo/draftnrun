from typing import Any, Type

from pydantic import BaseModel

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


class GraphRunnerBlockInputs(BaseModel):
    messages: Any = None

    model_config = {"extra": "allow"}


class GraphRunnerBlockOutputs(BaseModel):
    output: Any = None

    model_config = {"extra": "allow"}


class GraphRunnerBlock(Component):
    migrated = True

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return GraphRunnerBlockInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return GraphRunnerBlockOutputs

    @classmethod
    def get_canonical_ports(cls) -> dict[str, str | None]:
        return {"input": "messages", "output": "output"}

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

    async def _run_without_io_trace(
        self,
        inputs: GraphRunnerBlockInputs,
        ctx: dict,
    ) -> GraphRunnerBlockOutputs:
        input_data = inputs.model_dump(exclude_none=True)

        # TODO (dynamic I/O): Remove this string wrapping once project_reference supports
        # dynamic ports inherited from the inner project's schema. With dynamic ports,
        # the canonical input will match the inner project's fields directly and callers
        # will never coerce a string into the messages field.
        if isinstance(input_data.get("messages"), str):
            input_data["messages"] = [{"role": "user", "content": input_data["messages"]}]

        # TODO (legacy cleanup): GraphRunner.run() still returns AgentPayload via collect_legacy_outputs().
        # Once GraphRunner returns NodeData instead, replace this block with:
        #   result: NodeData = await self._graph_runner.run(input_data)
        #   return GraphRunnerBlockOutputs(output=result.data.get("output"))
        result: AgentPayload = await self._graph_runner.run(input_data)
        output = result.last_message.content if result.messages else None
        return GraphRunnerBlockOutputs(output=output)

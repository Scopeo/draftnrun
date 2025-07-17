import logging

from engine.agent.agent import Agent
from engine.agent.data_structures import AgentPayload, SplitPayload, ToolDescription, ComponentAttributes
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)


DEFAULT_MERGER_TOOL_DESCRIPTION = ToolDescription(
    name="merger",
    description="Merges multiple content chunks into a single output",
    tool_properties={},
    required_tool_properties=[],
)


class Merger(Agent):
    """Merges multiple AgentPayload instances into a single AgentPayload."""

    def __init__(
        self,
        trace_manager: TraceManager,
        tool_description: ToolDescription,
        component_attributes: ComponentAttributes,
        separator: str = "\n",
        **kwargs,
    ):
        super().__init__(trace_manager, tool_description, component_attributes, **kwargs)
        self.separator = separator

    async def _run_without_io_trace(self, *inputs: AgentPayload | SplitPayload, **kwargs) -> AgentPayload:
        """
        Merge multiple AgentPayload instances into a single AgentPayload.

        This takes multiple inputs (from the GraphRunner's _gather_inputs)
        and combines them into a single output.
        """
        if not inputs:
            raise ValueError("Merger requires at least one input")
        all_inputs = []
        for input_payload in inputs:
            if isinstance(input_payload, AgentPayload):
                all_inputs.append(input_payload)
            else:
                all_inputs.extend(input_payload.agent_payloads)

        # Collect the content from the last message of each input payload
        contents_to_merge = []
        merged_artifacts = {}
        errors = []
        for input_payload in all_inputs:
            contents_to_merge.append(input_payload.content)
            if input_payload.artifacts:
                for key, value in input_payload.artifacts.items():
                    if key not in merged_artifacts:
                        merged_artifacts[key] = []
                    merged_artifacts[key].append(value)
            if input_payload.error:
                errors.append(input_payload.error)

        # Merge the contents
        merged_content = self.separator.join(contents_to_merge)
        errors = self.separator.join(errors) if errors else ""

        output_payload = AgentPayload(messages=merged_content, error=errors, artifacts=merged_artifacts)

        # Log trace event
        self.log_trace_event(f"Merged {len(inputs)} inputs into one output")

        return output_payload

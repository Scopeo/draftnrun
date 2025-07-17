import logging
from typing import Optional

from engine.agent.agent import Agent
from engine.agent.data_structures import AgentPayload, ToolDescription, SplitPayload, ComponentAttributes
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)


DEFAULT_SPLITTER_TOOL_DESCRIPTION = ToolDescription(
    name="splitter",
    description=(
        "Splits content into multiple chunks based on delimiter or chunk size. "
        "Defaults to splitting by paragraphs (\\n\\n) if no parameters are provided."
    ),
    tool_properties={},
    required_tool_properties=[],
)


class Splitter(Agent):
    """Splits an AgentPayload into multiple AgentPayload instances based on delimiter or chunk size."""

    def __init__(
        self,
        trace_manager: TraceManager,
        tool_description: ToolDescription,
        component_attributes: ComponentAttributes,
        delimiter: Optional[str] = None,
        chunk_size: Optional[int] = None,
        **kwargs,
    ):
        super().__init__(trace_manager, tool_description, component_attributes, **kwargs)

        # If neither parameter is provided, use a default delimiter for paragraph splitting
        if delimiter is None and chunk_size is None:
            delimiter = "\n\n"

        if delimiter is not None and chunk_size is not None:
            raise ValueError("Only one of delimiter or chunk_size can be provided")

        self.delimiter = delimiter
        self.chunk_size = chunk_size

    def _split_content(self, content: str) -> list[str]:
        """Split the content based on the configured method."""

        if self.delimiter is not None:
            # Split by delimiter
            chunks = content.split(self.delimiter)
            # Remove empty chunks
            return [chunk for chunk in chunks if chunk]
        else:
            # Split by chunk size
            if not content:
                return []
            chunks = []
            for i in range(0, len(content), self.chunk_size):
                chunks.append(content[i : i + self.chunk_size])
            return chunks

    async def _run_without_io_trace(self, *inputs: AgentPayload, **kwargs) -> SplitPayload:
        """
        Split the input AgentPayload into multiple AgentPayload instances.

        Note: This returns a list of AgentPayload, which differs from the standard Agent pattern.
        The GraphRunner will need to handle this special case.
        """
        if not inputs:
            raise ValueError("Splitter requires at least one input")

        input_payload = inputs[0]

        # Split the content
        chunks = self._split_content(input_payload.main_content)

        # Create a new AgentPayload for each chunk
        output_payloads = []
        for chunk in chunks:
            new_payload = AgentPayload(
                messages=chunk,
                error=input_payload.error,
                artifacts=input_payload.artifacts.copy(),
                is_final=input_payload.is_final,
            )
            output_payloads.append(new_payload)

        # Log trace event
        self.log_trace_event(f"Split input into {len(output_payloads)} chunks")

        return SplitPayload(agent_payloads=output_payloads)

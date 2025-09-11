from typing import List
from engine.agent.agent import Agent
from engine.agent.types import AgentPayload, ToolDescription, ComponentAttributes, ChatMessage
from engine.graph_runner.graph_runner import GraphRunner
from engine.trace.trace_manager import TraceManager


def _normalize_escape_sequences(text: str) -> str:
    """
    Convert escaped sequences to their actual characters.
    This function can be extended to handle more escape sequences as needed.

    Args:
        text: String that may contain escaped sequences

    Returns:
        String with escaped sequences converted to actual characters
    """
    replacements = {
        "\\n": "\n",
        "\\t": "\t",
        "\\r": "\r",
    }

    result = text
    for escaped, actual in replacements.items():
        result = result.replace(escaped, actual)

    return result


DEFAULT_CHUNK_PROCESSOR_TOOL_DESCRIPTION = ToolDescription(
    name="Chunk Processor",
    description="Process data in chunks using a graph workflow",
    tool_properties={},
    required_tool_properties=[],
)


class ChunkProcessor(Agent):
    """
    An agent that processes data by splitting it into chunks, running a graph workflow
    on each chunk, and then merging the results.
    """

    def __init__(
        self,
        trace_manager: TraceManager,
        graph_runner: GraphRunner,
        component_attributes: ComponentAttributes,
        split_char: str = "\n\n",
        join_char: str = "\n\n",
        tool_description: ToolDescription = DEFAULT_CHUNK_PROCESSOR_TOOL_DESCRIPTION,
    ):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self._graph_runner = graph_runner
        self._split_char = _normalize_escape_sequences(split_char)
        self._join_char = _normalize_escape_sequences(join_char)

    def _split(self, input_payload: AgentPayload) -> List[AgentPayload]:
        """Split AgentPayload into multiple AgentPayloads for chunk processing."""
        content: str = input_payload.last_message.content or ""
        if not content.strip():
            return []

        parts = content.split(self._split_char)

        # Build payloads for non-empty parts
        chunk_payloads: List[AgentPayload] = []
        for part in parts:
            if part and part.strip():
                chunk_payloads.append(AgentPayload(messages=[ChatMessage(role="user", content=part.strip())]))

        return chunk_payloads

    def _merge(self, results: List[AgentPayload]) -> AgentPayload:
        """Merge multiple AgentPayload results into a single AgentPayload."""
        if not results:
            return AgentPayload(messages=[ChatMessage(role="assistant", content="")])

        merged_content_parts: List[str] = []
        for result in results:
            if result.last_message.content:
                merged_content_parts.append(result.last_message.content)

        merged_content = self._join_char.join(merged_content_parts)

        return AgentPayload(messages=[ChatMessage(role="assistant", content=merged_content)])

    async def _run_without_io_trace(self, *inputs: AgentPayload, **kwargs) -> AgentPayload:
        """
        Run the chunk processor:
        1. Split input into chunks
        2. Run graph runner on each chunk
        3. Merge results
        Supports only 1 input
        """
        input_data: AgentPayload | dict = inputs[0]
        if isinstance(input_data, dict):
            input_data = AgentPayload(**input_data)

        chunk_payloads = self._split(input_data)
        if not chunk_payloads:
            return AgentPayload(messages=[ChatMessage(role="assistant", content="")])

        results: List[AgentPayload] = []
        for chunk_payload in chunk_payloads:
            self._graph_runner.reset()
            result = await self._graph_runner.run(chunk_payload)

            if not isinstance(result, AgentPayload):
                raise ValueError(
                    f"ChunkProcessor: GraphRunner must return an AgentPayload, got {type(result)}",
                )

            results.append(result)

        return self._merge(results)

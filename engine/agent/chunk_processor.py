from copy import deepcopy
from typing import List
from engine.agent.agent import Agent
from engine.agent.types import AgentPayload, ToolDescription, ComponentAttributes, ChatMessage
from engine.graph_runner.graph_runner import GraphRunner
from engine.trace.trace_manager import TraceManager


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
        n_chunks: int = 3,
        join_char: str = "\n\n",
        tool_description: ToolDescription = DEFAULT_CHUNK_PROCESSOR_TOOL_DESCRIPTION,
    ):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self._graph_runner = graph_runner
        self._n_chunks = n_chunks
        self._join_char = join_char

    def _split(self, input_payload: AgentPayload) -> List[AgentPayload]:
        """Split AgentPayload into multiple AgentPayloads for chunk processing."""
        if not input_payload.messages:
            return []

        # Get the content from the last message
        content: str = input_payload.messages[-1].content or ""
        if not content.strip():
            return []

        # Simple splitting by words for n_chunks
        words = content.split()
        if not words:
            return []

        if len(words) <= self._n_chunks:
            # If we have fewer words than chunks, create one chunk per word
            return [AgentPayload(messages=[ChatMessage(role="user", content=word)]) for word in words]

        # Calculate chunk size
        chunk_size = len(words) // self._n_chunks
        remainder = len(words) % self._n_chunks

        chunks = []
        start = 0

        for i in range(self._n_chunks):
            # Add one extra word to the first 'remainder' chunks
            current_chunk_size = chunk_size + (1 if i < remainder else 0)
            end = start + current_chunk_size

            chunk_words = words[start:end]
            if chunk_words:
                chunk_content = " ".join(chunk_words)
                chunks.append(AgentPayload(messages=[ChatMessage(role="user", content=chunk_content)]))

            start = end

        return chunks

    def _merge(self, results: List[AgentPayload]) -> AgentPayload:
        """Merge multiple AgentPayload results into a single AgentPayload."""
        if not results:
            return AgentPayload(messages=[ChatMessage(role="assistant", content="")])

        # Extract content from all results
        merged_content_parts = []

        for result in results:
            if result.messages:
                # Get the last message content from each result
                last_message = result.messages[-1]
                if last_message.content:
                    merged_content_parts.append(last_message.content)

        # Join all parts with the join character
        merged_content = self._join_char.join(merged_content_parts)

        return AgentPayload(messages=[ChatMessage(role="assistant", content=merged_content)])

    async def _run_without_io_trace(self, *inputs: AgentPayload, **kwargs) -> AgentPayload:
        """
        Run the chunk processor:
        1. Split input into chunks
        2. Run graph runner on each chunk
        3. Merge results
        """
        input_data: AgentPayload = inputs[0]

        chunk_payloads = self._split(input_data)
        if not chunk_payloads:
            return AgentPayload(messages=[ChatMessage(role="assistant", content="")])

        results: List[AgentPayload] = []
        for chunk_payload in chunk_payloads:
            # TODO: Make a reset state method for the graph runner
            graph_runner_copy = deepcopy(self._graph_runner)
            result = await graph_runner_copy.run(chunk_payload)

            if not isinstance(result, AgentPayload):
                raise ValueError(
                    f"ChunkProcessor: GraphRunner must return an AgentPayload, got {type(result)}",
                )

            results.append(result)

        return self._merge(results)

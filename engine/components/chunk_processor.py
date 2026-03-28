from typing import Any, List, Type

from pydantic import BaseModel

from engine.components.component import Component
from engine.components.types import AgentPayload, ComponentAttributes, ToolDescription
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


class ChunkProcessorInputs(BaseModel):
    input: Any = None

    model_config = {"extra": "allow"}


class ChunkProcessorOutputs(BaseModel):
    output: Any = None

    model_config = {"extra": "allow"}


class ChunkProcessor(Component):
    """
    An agent that processes data by splitting it into chunks, running a graph workflow
    on each chunk, and then merging the results.
    """

    migrated = True

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return ChunkProcessorInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return ChunkProcessorOutputs

    @classmethod
    def get_canonical_ports(cls) -> dict[str, str | None]:
        return {"input": "input", "output": "output"}

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

    def _split(self, content: str) -> List[str]:
        """Split a string into a list of non-empty stripped chunks."""
        if not content.strip():
            return []
        return [part.strip() for part in content.split(self._split_char) if part and part.strip()]

    def _merge(self, results: List[str]) -> str:
        """Merge a list of string results into a single string using the join character."""
        return self._join_char.join(results)

    async def _run_without_io_trace(
        self,
        inputs: ChunkProcessorInputs,
        ctx: dict,
    ) -> ChunkProcessorOutputs:
        """
        Run the chunk processor:
        1. Split input into chunks
        2. Run graph runner on each chunk
        3. Merge results
        """
        # TODO (dynamic I/O): Remove this adaptation once chunk_processor supports dynamic ports
        # inherited from the inner project's schema. With dynamic ports, the canonical input will
        # carry the correct string type and this bridge becomes unnecessary.
        if isinstance(inputs.input, str):
            content = inputs.input
        elif isinstance(inputs.input, list) and inputs.input:
            last = inputs.input[-1]
            content = (last.get("content") if isinstance(last, dict) else getattr(last, "content", "")) or ""
        else:
            content = ""
        chunks = self._split(content)
        if not chunks:
            return ChunkProcessorOutputs(output="")

        results: List[str] = []
        for chunk in chunks:
            chunk_data: dict = {"input": chunk}

            # TODO (dynamic I/O): Remove this adaptation once chunk_processor supports dynamic ports
            # inherited from the inner project's schema. With dynamic ports, the canonical input will
            # match the inner project's expected fields (e.g. "messages" for Agent projects) and this
            # bridge becomes unnecessary.
            chunk_data["messages"] = [{"role": "user", "content": chunk}]

            self._graph_runner.reset()

            # TODO (legacy cleanup): GraphRunner.run() still returns AgentPayload via collect_legacy_outputs().
            # Once GraphRunner returns NodeData instead, replace this block with:
            #   result: NodeData = await self._graph_runner.run(chunk_data)
            #   results.append(result.data.get("output", ""))
            result: AgentPayload = await self._graph_runner.run(chunk_data)
            output = (result.last_message.content or "") if result.messages else ""
            results.append(output)

        return ChunkProcessorOutputs(output=self._merge(results))

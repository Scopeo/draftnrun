from typing import Optional
from pathlib import Path
from collections import defaultdict

from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes

from engine.agent.agent import (
    Agent,
    AgentPayload,
    ChatMessage,
    ComponentAttributes,
    ToolDescription,
)

from engine.agent.rag.document_search import DocumentSearch
from engine.trace.trace_manager import TraceManager
from engine.agent.synthesizer import Synthesizer
from engine.agent.agent import DocumentContent

DEFAULT_DOCUMENT_ENHANCED_LLM_CALL_TOOL_DESCRIPTION = ToolDescription(
    name="Document_enhanced_llm_call",
    description=(
        "Use this function when the user refers to one or more specific documents (e.g., to get a summary, use as a"
        " template/example, or ask detailed questions about a known document). "
        "This function loads the documents directly and uses them to answer the query."
        " Must be used if the user mentions a document name or asks for a summary of a specific file, or to answer"
        "a query related to a specific document. The query must be fully detailed and include "
        "all essential words, including interrogative adverbs."
    ),
    tool_properties={
        "query_text": {
            "type": "string",
            "description": (
                "A full-length, well-formed search query preserving all key elements from the user's input."
            ),
        },
        "document_names": {
            "type": "array",
            "description": ("A list of file names that the tool can load in the context to answer the query."),
            "items": {"type": "string", "enum": []},
            "minItems": 1,
        },
    },
    required_tool_properties=["document_names"],
)


def build_context_from_documents_content(documents_content: list[DocumentContent]) -> str:
    return "\n".join([f"# Document {doc.document_name}: {doc.content_document}" for doc in documents_content])


def nested_tree():
    """Python function to create a nested dictionary structure.
    When trying to call for instance tree['foo']['bar'], it will create the 'foo' and 'bar' keys
    automatically
    """
    return defaultdict(nested_tree)


def format_tree(node, prefix=""):
    lines = []
    entries = sorted(node.keys())
    for i, entry in enumerate(entries):
        is_last = i == len(entries) - 1
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{entry}")
        extension = "    " if is_last else "│   "
        lines.extend(format_tree(node[entry], prefix + extension))
    return lines


def build_ascii_tree(paths: list[str]) -> str:
    """
    Takes a list of file paths and builds an ASCII tree of folders and file names.

    Args:
        paths (list[str]): List of file paths (can be absolute or relative).

    Returns:
        str: ASCII tree representation of the folder structure.
    """
    root = nested_tree()

    # Build nested dictionary
    for path_str in paths:
        parts = Path(path_str).parts
        node = root
        for part in parts:
            node = node[part]

    return "\n".join(format_tree(root))


class DocumentEnhancedLLMCallAgent(Agent):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.CHAIN.value
    """
    This is an Document capable RAG that takes an file name
    and returns a response that is based on the OCR content of the file as a context.
    """

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        tool_description: ToolDescription,
        synthesizer: Synthesizer,
        document_search: DocumentSearch,
    ) -> None:
        super().__init__(
            trace_manager=trace_manager,
            component_attributes=component_attributes,
            tool_description=tool_description,
            synthesizer=synthesizer,
        )
        self._synthesizer = synthesizer
        self._document_search = document_search
        self.tree_of_documents = build_ascii_tree(self._document_search.get_documents_names())
        self._update_description_tool(self._document_search)

    def _update_description_tool(self, document_search: DocumentSearch) -> ToolDescription:
        self.tool_description.tool_properties["document_names"]["items"][
            "enum"
        ] = document_search.get_documents_names()
        self.tool_description.description = (
            self.tool_description.description
            + "\n\n Here is the list of documents available: \n\n"
            + self.tree_of_documents
        )

    async def _run_without_trace(
        self,
        *inputs: AgentPayload,
        query_text: Optional[str] = None,
        document_names: Optional[list[str]] = None,
    ) -> AgentPayload:
        agent_input = inputs[0]
        content = query_text or agent_input.last_message.content
        # TODO : improve with fuzzy matching on document name?
        if content is None:
            raise ValueError("No content provided for the DocumentEnhancedLLMcall tool.")
        if document_names is None:
            raise ValueError("No document names provided for the DocumentEnhancedLLMcall tool.")
        documents_chunks = self._document_search.get_documents(documents_name=document_names)

        response = await self._synthesizer.get_response(
            chunks=documents_chunks,
            query_str=content,
        )

        for i, document_content in enumerate(documents_chunks):
            self.log_trace(
                {
                    f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.content": document_content.content,
                    f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.id": document_content.document_name,
                }
            )

        return AgentPayload(
            messages=[ChatMessage(role="assistant", content=response.response)],
            is_final=response.is_successful,
            artifacts={"documents": [doc.model_dump() for doc in documents_chunks]},
        )

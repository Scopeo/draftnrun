import logging
from typing import Optional

from engine.agent.data_structures import ToolDescription
from engine.agent.rag.rag import RAG, format_rag_tool_description
from engine.agent.rag.retriever import Retriever, DummyRetriever
from engine.qdrant_service import QdrantService, QdrantCollectionSchema
from engine.trace.trace_manager import TraceManager
from engine.agent.synthesizer import Synthesizer
from engine.agent.synthesizer_prompts import get_synthetizer_prompt_template_slack
from engine.llm_services.llm_service import CompletionService

LOGGER = logging.getLogger(__name__)

DEFAULT_MAX_RETRIEVED_CHUNKS = 10


def build_default_rag_agent(
    completion_service: CompletionService,
    trace_manager: TraceManager,
    source_name: str,
    collection_schema: Optional[QdrantCollectionSchema] = None,
    tool_description: Optional[ToolDescription] = None,
    synthetizer_prompt: Optional[str] = None,
    max_retrieved_chunks: int = DEFAULT_MAX_RETRIEVED_CHUNKS,
) -> RAG:
    if collection_schema is None:
        collection_schema = QdrantCollectionSchema(
            chunk_id_field="CHUNK_ID",
            content_field="CHUNK",
            file_id_field="URL",
        )
    if tool_description is None:
        tool_description = format_rag_tool_description(source_name)
    if synthetizer_prompt is None:
        synthetizer_prompt = get_synthetizer_prompt_template_slack()
    qdrant_service = QdrantService.from_defaults(
        completion_service=completion_service,
        default_collection_schema=collection_schema,
    )
    retriever = Retriever(
        trace_manager=trace_manager,
        collection_name=source_name,
        qdrant_service=qdrant_service,
        max_retrieved_chunks=max_retrieved_chunks,
    )
    synthesizer = Synthesizer(
        completion_service=completion_service,
        trace_manager=trace_manager,
        prompt_template=synthetizer_prompt,
    )
    return RAG(
        trace_manager=trace_manager,
        tool_description=tool_description,
        retriever=retriever,
        synthesizer=synthesizer,
    )


def build_slack_rag_agent(
    completion_service: CompletionService,
    trace_manager: TraceManager,
    source_name: str = "slack",
    max_retrieved_chunks: int = DEFAULT_MAX_RETRIEVED_CHUNKS,
) -> RAG:
    collection_schema = QdrantCollectionSchema(
        chunk_id_field="THREAD_TS",
        content_field="CONTENT",
        file_id_field="CHANNELS",
    )
    return build_default_rag_agent(
        completion_service=completion_service,
        trace_manager=trace_manager,
        source_name=source_name,
        collection_schema=collection_schema,
        max_retrieved_chunks=max_retrieved_chunks,
    )


def build_notion_rag_agent(
    completion_service: CompletionService,
    trace_manager: TraceManager,
    source_name: str = "notion",
    max_retrieved_chunks: int = DEFAULT_MAX_RETRIEVED_CHUNKS,
) -> RAG:
    collection_schema = QdrantCollectionSchema(
        chunk_id_field="CHUNK_ID",
        content_field="CONTENT",
        file_id_field="URL",
    )
    return build_default_rag_agent(
        completion_service=completion_service,
        trace_manager=trace_manager,
        source_name=source_name,
        collection_schema=collection_schema,
        max_retrieved_chunks=max_retrieved_chunks,
    )


def build_s3_rag_agent(
    completion_service: CompletionService,
    trace_manager: TraceManager,
    source_name: str = "s3",
    max_retrieved_chunks: int = DEFAULT_MAX_RETRIEVED_CHUNKS,
) -> RAG:
    tool_description = format_rag_tool_description(source_name)
    collection_schema = QdrantCollectionSchema(
        chunk_id_field="CHUNK_ID",
        content_field="CHUNK",
        file_id_field="WEB_VIEW_LINK",
        metadata_fields_to_keep={
            "PAGE_NUMBER",
            "FILE_NAME",
        },
    )
    qdrant_service = QdrantService.from_defaults(
        completion_service=completion_service,
        default_collection_schema=collection_schema,
    )
    retriever = Retriever(
        trace_manager=trace_manager,
        collection_name=source_name,
        qdrant_service=qdrant_service,
        max_retrieved_chunks=max_retrieved_chunks,
    )
    synthesizer = Synthesizer(completion_service=completion_service, trace_manager=trace_manager)
    return RAG(
        trace_manager=trace_manager,
        tool_description=tool_description,
        retriever=retriever,
        synthesizer=synthesizer,
    )


def build_personal_doc_rag_agent(completion_service: CompletionService, trace_manager: TraceManager) -> RAG:
    tool_description = ToolDescription(
        name="search_all_documents",
        description=(
            "Searches a database containing emails, pdf documents, "
            "and call transcripts to retrieve relevant information "
            "related to the user's work documents. This tool is useful "
            "to gather all information about a specific topic or to "
            "find examples of how to write a specific type of document."
        ),
        tool_properties={
            "query_text": {
                "type": "string",
                "description": "The search query for the knowledge base.",
            },
            # TODO: Improve filter support: https://api.qdrant.tech/api-reference/search/points
            "filters": {
                "type": "object",
                "description": "The filters to apply to the search query.",
            },
        },
        required_tool_properties=[],
    )
    retriever = DummyRetriever(trace_manager=trace_manager, whole_knowledge_base=[])
    synthesizer = Synthesizer(completion_service=completion_service, trace_manager=trace_manager)
    return RAG(
        trace_manager=trace_manager,
        tool_description=tool_description,
        retriever=retriever,
        synthesizer=synthesizer,
    )

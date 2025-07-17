import re
from typing import Optional

from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes

from engine.agent.data_structures import (
    ChatMessage,
    AgentPayload,
    ComponentAttributes,
    SourceChunk,
    ToolDescription,
)
from engine.agent.rag.rag import RAG
from engine.agent.rag.reranker import Reranker
from engine.agent.rag.retriever import Retriever
from engine.trace.trace_manager import TraceManager
from engine.agent.synthesizer import Synthesizer
from engine.agent.hybrid_synthesizer import HybridSynthesizer
from engine.agent.utils import format_qdrant_filter
from engine.agent.rag.formatter import Formatter
from engine.agent.rag.chunk_selection import RelevantChunkSelector, RelevantChunk

PATTERN = r"Image Description:.*?<END_IMAGE_DESCRIPTION>"


class HybridRAG(RAG):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.CHAIN.value
    """
    This is an image-capable RAG that takes an image and text as inputs
    and returns a response that may include relevant image IDs.
    """

    def __init__(
        self,
        trace_manager: TraceManager,
        tool_description: ToolDescription,
        retriever: Retriever,
        synthesizer: Synthesizer,
        reranker: Reranker,
        hybrid_synthesizer: HybridSynthesizer,
        relevant_chunk_selector: RelevantChunkSelector,
        component_attributes: Optional[ComponentAttributes] = None,
        filtering_condition: str = "OR",
        formatter: Optional[Formatter] = None,
    ) -> None:
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            synthesizer=synthesizer,
            retriever=retriever,
            reranker=reranker,
            component_attributes=component_attributes,
        )
        self._synthesizer = synthesizer
        self._hybrid_synthesizer = hybrid_synthesizer
        self._relevant_chunk_selector = relevant_chunk_selector
        self._filtering_condition = filtering_condition
        self._formatter = formatter

    async def _run_without_io_trace(
        self,
        agent_input: AgentPayload,
        query_text: Optional[str] = None,
        filters: Optional[dict] = None,
    ) -> AgentPayload:
        content = query_text or agent_input.main_content
        if content is None:
            raise ValueError("No content provided for the RAG tool.")
        formatted_filters = format_qdrant_filter(filters, self._filtering_condition)
        chunks = await self._retriever.get_chunks(query_text=content, filters=formatted_filters)

        if self._reranker is not None:
            chunks = self._reranker.rerank(query=content, chunks=chunks)

        relevant_chunks = await self._relevant_chunk_selector.get_response(
            chunks=chunks,
            question=content,
        )
        relevant_image_sources, relevant_text_sources = process_relevant_sources(
            sources=chunks,
            chunk_selection_response=relevant_chunks,
        )
        responses_hybrid_synthesizer = await process_image_responses(
            relevant_image_sources=relevant_image_sources,
            hybrid_synthesizer=self._hybrid_synthesizer,
            query_str=content,
        )
        text_image_sources_for_synthesizer, images_to_show_user = get_all_sources_for_synthesizer(
            relevant_image_sources=relevant_image_sources,
            relevant_text_sources=relevant_text_sources,
            useful_answers_images=responses_hybrid_synthesizer,
        )

        synthesized_response = await self._synthesizer.get_response(
            chunks=text_image_sources_for_synthesizer,
            query_str=content,
        )
        if self._formatter is not None:
            synthesized_response = self._formatter.format(synthesized_response)

        for i, source in enumerate(text_image_sources_for_synthesizer):
            self.log_trace(
                {
                    f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.content": source.content,
                    f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.id": source.name,
                }
            )

        return AgentPayload(
            messages=[ChatMessage(role="assistant", content=synthesized_response.response)],
            artifacts=(
                {"image_id": images_to_show_user, "sources": synthesized_response.sources}
                if images_to_show_user
                else {"sources": synthesized_response.sources}
            ),
            is_final=synthesized_response.is_successful,
        )


def process_relevant_sources(
    sources: list[SourceChunk], chunk_selection_response: RelevantChunk
) -> tuple[list[SourceChunk], list[SourceChunk]]:
    relevant_image_sources = []
    relevant_text_sources = []
    added_sources_ids = set()

    if chunk_selection_response.response:
        for i, source in enumerate(sources):
            if i + 1 in chunk_selection_response.response and i not in added_sources_ids:
                image_ids = source.metadata.get("image_ids", [])
                added_sources_ids.add(i)

                if image_ids:
                    for image_id in image_ids:
                        modified_content = re.sub(PATTERN, f"Image ID: {image_id}", source.content, flags=re.DOTALL)
                    relevant_image_sources.append(
                        SourceChunk(
                            name=source.name,
                            document_name=source.name,
                            content=modified_content,
                            url=source.url,
                            metadata=source.metadata,
                        )
                    )
                else:
                    relevant_text_sources.append(source)
    return relevant_image_sources, relevant_text_sources


async def process_image_responses(
    relevant_image_sources: list[SourceChunk],
    hybrid_synthesizer: HybridSynthesizer,
    query_str: str,
) -> list[dict]:
    useful_answers_images = []
    for image_source in relevant_image_sources:
        image_ids = image_source.metadata.get("image_ids", [])
        for image_id in image_ids:
            response = await hybrid_synthesizer.get_response(
                image_id=image_id,
                chunks=[image_source],
                query_str=query_str,
            )
            if response.score_image <= 2:
                useful_answers_images.append({response.image_id: response.response})
    return useful_answers_images


def get_all_sources_for_synthesizer(
    relevant_image_sources: list[SourceChunk],
    relevant_text_sources: list[SourceChunk],
    useful_answers_images: list[dict],
) -> tuple[list[SourceChunk], set]:
    all_sources = []
    images_to_show_user = set()

    for relevant_image_source in relevant_image_sources:
        collected_responses = []
        if useful_answers_images:
            for useful_answer in useful_answers_images:
                for image_id, response in useful_answer.items():
                    if image_id not in images_to_show_user:
                        collected_responses.append(response)
                        images_to_show_user.add(image_id)

        if collected_responses:
            relevant_image_source.content = "ANSWER USING IMAGES: " + " ".join(collected_responses)

        all_sources.append(relevant_image_source)

    all_sources.extend(relevant_text_sources)

    return all_sources, images_to_show_user

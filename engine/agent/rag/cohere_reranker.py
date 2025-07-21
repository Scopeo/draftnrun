import logging
from typing import Optional

import cohere

from engine.agent.agent import ComponentAttributes, SourceChunk
from engine.agent.rag.reranker import Reranker
from engine.trace.trace_manager import TraceManager
from settings import settings

LOGGER = logging.getLogger(__name__)


class CohereReranker(Reranker):
    def __init__(
        self,
        trace_manager: TraceManager,
        cohere_api_key: Optional[str] = None,
        cohere_model: str = "rerank-multilingual-v3.0",
        num_doc_reranked: int = 5,
        score_threshold: float = 0.0,
        component_attributes: Optional[ComponentAttributes] = None,
    ):
        super().__init__(
            trace_manager,
            model=cohere_model,
            component_attributes=component_attributes,
        )
        if cohere_api_key is None:
            cohere_api_key = settings.COHERE_API_KEY
        self._async_cohere_client = cohere.AsyncClientV2(cohere_api_key)
        self._num_doc_reranked = num_doc_reranked
        self._score_threshold = score_threshold

    async def _rerank_without_trace(self, query, chunks: list[SourceChunk]) -> list[SourceChunk]:
        if not chunks:
            LOGGER.warning("No documents to rerank. The chunks list is empty.")
            return []
        response = await self._async_cohere_client.rerank(
            model=self._model,
            query=query,
            documents=[chunk.content for chunk in chunks],
            top_n=self._num_doc_reranked,
        )
        reranked_chunks = [
            chunks[result.index] for result in response.results if result.relevance_score >= self._score_threshold
        ]
        for chunk, result in zip(reranked_chunks, response.results):
            chunk.metadata["reranked_score"] = result.relevance_score
        LOGGER.info(f"Reranked {len(reranked_chunks)} chunks")
        return reranked_chunks

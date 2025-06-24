import asyncio

from pydantic import BaseModel

from engine.agent.synthesizer_prompts import get_hybrid_synthetizer_prompt_template
from engine.agent.synthesizer import Synthesizer
from engine.llm_services.llm_service import LLMService
from engine.trace.trace_manager import TraceManager
from engine.agent.build_context import build_context_from_source_chunks
from engine.agent.agent import SourceChunk, SourcedResponse


class ResponseLLM(BaseModel):
    response: str
    score_image: int
    image_id: str


class HybridSynthesizerResponse(SourcedResponse):
    score_image: int
    image_id: str


class HybridSynthesizer(Synthesizer):
    """
    This is a hybrid synthesizer that takes an image and text as inputs
    and returns a response along with an image relevance score and image ID.
    """

    def __init__(
        self,
        llm_service: LLMService,
        trace_manager: TraceManager,
        prompt_template: str = get_hybrid_synthetizer_prompt_template(),
        response_format: BaseModel = ResponseLLM,
    ):
        super().__init__(llm_service, trace_manager)
        self._prompt_template = prompt_template
        self.response_format = response_format

    async def get_response(
        self,
        image_id: str,
        chunks: list[SourceChunk],
        query_str: str,
    ) -> HybridSynthesizerResponse:
        context_str = build_context_from_source_chunks(
            sources=chunks,
            llm_metadata_keys=chunks[0].metadata.keys() if chunks else [],
        )
        with open(image_id, "rb") as image_file:
            encoded_image = image_file.read()

        response_using_image = await self._llm_service.async_get_image_description(
            image_content_list=[encoded_image],
            text_prompt=self._prompt_template.format(
                image_id=image_id,
                context_str=context_str,
                query_str=query_str,
            ),
            response_format=self.response_format,
        )
        return HybridSynthesizerResponse(
            response=response_using_image.response,
            score_image=response_using_image.score_image,
            image_id=image_id,
            sources=chunks,
        )

    def get_response_sync(
        self,
        image_id: str,
        chunks: list[SourceChunk],
        query_str: str,
    ) -> HybridSynthesizerResponse:
        return asyncio.run(self.get_response(
            image_id=image_id,
            chunks=chunks,
            query_str=query_str,
        ))

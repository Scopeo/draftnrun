from typing import Callable, Optional
from uuid import UUID

from pydantic import BaseModel

from engine.components.build_context import build_context_from_source_chunks
from engine.components.synthesizer import Synthesizer
from engine.components.synthesizer_prompts import get_hybrid_synthetizer_prompt_template
from engine.components.types import ComponentAttributes, SourceChunk, SourcedResponse
from engine.llm_services.llm_service import CompletionService
from engine.llm_services.utils import get_llm_provider_and_model
from engine.trace.trace_manager import TraceManager


class ResponseLLM(BaseModel):
    response: str
    score_image: int
    image_id: str


class HybridSynthesizerResponse(SourcedResponse):
    score_image: int
    image_id: str


class HybridSynthesizer(Synthesizer):
    def __init__(
        self,
        trace_manager: TraceManager,
        temperature: float = 1.0,
        llm_api_key: Optional[str] = None,
        verbosity: Optional[str] = None,
        reasoning: Optional[str] = None,
        model_id_resolver: Optional[Callable[[str], Optional[UUID]]] = None,
        prompt_template: str = get_hybrid_synthetizer_prompt_template(),
        response_format: BaseModel = ResponseLLM,
        component_attributes: Optional[ComponentAttributes] = None,
    ):
        super().__init__(
            trace_manager=trace_manager,
            temperature=temperature,
            llm_api_key=llm_api_key,
            verbosity=verbosity,
            reasoning=reasoning,
            model_id_resolver=model_id_resolver,
            component_attributes=component_attributes,
        )
        self._prompt_template = prompt_template
        self.response_format = response_format

    async def get_response(
        self,
        image_id: str,
        chunks: list[SourceChunk],
        query_str: str,
        completion_model: str,
    ) -> HybridSynthesizerResponse:

        provider, model_name = get_llm_provider_and_model(completion_model)
        model_id = self._model_id_resolver(model_name)

        completion_service = CompletionService(
            provider=provider,
            model_name=model_name,
            trace_manager=self.trace_manager,
            temperature=self._temperature,
            api_key=self._llm_api_key,
            verbosity=self._verbosity,
            reasoning=self._reasoning,
            model_id=model_id,
        )

        context_str = build_context_from_source_chunks(sources=chunks)
        with open(image_id, "rb") as image_file:
            encoded_image = image_file.read()

        response_using_image = await completion_service.get_image_description_async(
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

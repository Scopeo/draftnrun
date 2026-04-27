from typing import Callable, Optional
from uuid import UUID

from pydantic import BaseModel

from engine.components.build_context import build_context_from_source_chunks
from engine.components.close_mixin import CloseMixin
from engine.components.types import ComponentAttributes, SourceChunk, SourcedResponse
from engine.llm_services.llm_service import CompletionService
from engine.llm_services.utils import get_llm_provider_and_model
from engine.trace.trace_manager import TraceManager

CHUNK_SELECTION_PROMPT = (
    "You will be given multiple sources of information which will contain image descrptions. "
    "Your task is to select the most relevant text sources that need further review based on the given question."
    "To select relevant text sources, add their numbers to the 'relevant_text_source_numbers' field. \n\n"
    "Here are the available sources: \n{sources}\n\n"
    "Question: {question}"
)


class RelevantChunk(BaseModel):
    relavent_text_source_numbers: list[int]


class RelevantChunkSelector(CloseMixin):
    def __init__(
        self,
        trace_manager: TraceManager,
        temperature: float = 1.0,
        llm_api_key: Optional[str] = None,
        verbosity: Optional[str] = None,
        reasoning: Optional[str] = None,
        model_id_resolver: Optional[Callable[[str], Optional[UUID]]] = None,
        prompt_template: str = CHUNK_SELECTION_PROMPT,
        response_format: BaseModel = RelevantChunk,
        component_attributes: Optional[ComponentAttributes] = None,
    ):
        self.trace_manager = trace_manager
        self._temperature = temperature
        self._llm_api_key = llm_api_key
        self._verbosity = verbosity
        self._reasoning = reasoning
        self._model_id_resolver = model_id_resolver or (lambda _: None)
        self._prompt_template = prompt_template
        self._response_format = response_format
        self.component_attributes = component_attributes or ComponentAttributes(
            component_instance_name=self.__class__.__name__
        )

    async def get_response(
        self,
        chunks: list[SourceChunk],
        question: str,
        completion_model: str,
    ) -> RelevantChunk:

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

        sources = build_context_from_source_chunks(sources=chunks)
        response = await completion_service.constrained_complete_with_pydantic_async(
            messages=[
                {
                    "role": "system",
                    "content": self._prompt_template.format(
                        sources=sources,
                        question=question,
                    ),
                },
            ],
            response_format=self._response_format,
        )
        return SourcedResponse(
            response=response.relavent_text_source_numbers,
            source_chunks=chunks,
        )
